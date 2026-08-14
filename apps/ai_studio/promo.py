import logging
from typing import Any, Dict

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.pricing.models import UserPlan, UsageLog

from .services.renderer import SOCIAL_FORMATS, normalize_promo_props
from .services.renderer_dispatch import trigger_github_render

logger = logging.getLogger(__name__)


def build_promo_props(job) -> Dict[str, Any]:
    """
    Build the props object that Remotion's PromoVideo composition expects.

    This function first tries to use a promo_props/promoProps field from the
    job if one exists. Otherwise it builds the basic props from common job
    fields.
    """
    raw_props = getattr(job, "promo_props", None)

    if raw_props is None:
        raw_props = getattr(job, "promoProps", None)

    if raw_props is None:
        raw_props = {}

    if not isinstance(raw_props, dict):
        raw_props = {}

    props: Dict[str, Any] = dict(raw_props)

    field_map = {
        "headline": "headline",
        "subtext": "subtext",
        "ctaText": "cta_text",
        "price": "price",
        "brandName": "brand_name",
        "website": "website",
        "productImage": "product_image",
        "logoImage": "logo_image",
        "badge": "badge",
        "colors": "colors",
    }

    for prop_name, job_field in field_map.items():
        if prop_name not in props:
            value = getattr(job, job_field, None)
            if value is not None:
                props[prop_name] = value

    return normalize_promo_props(props)


def resolve_video_format(job) -> str:
    """
    Resolve the requested social-media video format from the job.
    Falls back to 'ig' if no valid format is stored on the job.
    """
    possible_fields = ("format_name", "video_format", "format", "aspect_ratio")
    format_name = None

    for field_name in possible_fields:
        value = getattr(job, field_name, None)
        if value:
            format_name = str(value).lower().strip()
            break

    if not format_name:
        format_name = "ig"

    if format_name not in SOCIAL_FORMATS:
        logger.warning(
            "Unknown video format '%s' for job %s. Falling back to 'ig'.",
            format_name, job.id,
        )
        format_name = "ig"

    return format_name


def _build_render_config(job, props: dict, format_name: str) -> Dict[str, Any]:
    format_config = SOCIAL_FORMATS[format_name]
    return {
        "compositionId": "PromoVideo",
        "inputProps": normalize_promo_props(props),
        "width": format_config.width,
        "height": format_config.height,
        "fps": format_config.fps,
        "durationInFrames": format_config.duration,
        "outputPath": f"/tmp/render-output/{job.id}.mp4",
        "mediaOrigin": settings.PUBLIC_BASE_URL,
        "concurrency": 2,
        "jpegQuality": 80,
        "x264Preset": "fast",
    }


def dispatch_job_video(job) -> None:
    """
    Dispatch a video-rendering job to GitHub Actions.

    Django creates the render configuration and sends it to GitHub.
    GitHub Actions performs the actual Remotion render, uploads the MP4
    to Cloudinary, and calls the Django callback when finished.
    """
    if job.video and default_storage.exists(job.video.name):
        logger.info("Job %s already has a rendered video. Skipping.", job.id)
        return

    props = build_promo_props(job)
    format_name = resolve_video_format(job)
    config = _build_render_config(job, props, format_name)

    job.stage = "rendering_video"
    job.status = "processing"
    job.save(update_fields=["stage", "status"])

    try:
        trigger_github_render(job_id=str(job.id), config=config)
        logger.info("GitHub Actions render dispatched successfully for job %s.", job.id)
    except Exception as exc:
        logger.exception("Failed to dispatch GitHub render for job %s.", job.id)
        job.status = "failed"
        job.stage = "video_dispatch_failed"
        job.error = str(exc)
        job.save(update_fields=["status", "stage", "error"])
        raise


def dispatch_preview_render(job, *, props: dict, format_name: str) -> None:
    """
    Like dispatch_job_video, but for one-off editor-preview exports where
    props are supplied directly by the caller rather than built from a
    persisted AIJob's fields.
    """
    config = _build_render_config(job, props, format_name)

    job.stage = "rendering_video"
    job.status = "processing"
    job.save(update_fields=["stage", "status"])

    try:
        trigger_github_render(job_id=str(job.id), config=config)
    except Exception as exc:
        job.status = "failed"
        job.stage = "video_dispatch_failed"
        job.error = str(exc)
        job.save(update_fields=["status", "stage", "error"])
        raise

def _track_usage(job) -> None:
    """
    Server-side usage tracking — the single source of truth for
    'a campaign was generated', triggered directly by render completion
    rather than a frontend fetch call that can silently fail.

    Idempotent by construction: relies on a DB-level unique constraint on
    UsageLog(campaign_id, action) — see apps/pricing/models.py — rather than
    a plain existence check. A separate SELECT-then-CREATE (the previous
    approach) is not race-safe: if the render callback fires twice for the
    same job (duplicate webhook delivery, GitHub Actions retry, etc.) two
    concurrent requests can both pass an .exists() check before either has
    written its row, and both go on to increment usage — which is exactly
    how 4 campaigns turned into 8 counted assets. get_or_create() below is
    atomic against the unique constraint: Django catches the IntegrityError
    from a losing concurrent insert and re-fetches instead, so only one
    caller ever sees created=True.
    """
    user_id = getattr(job, "user_id", None)
    if not user_id:
        logger.info("Job %s has no associated user, skipping usage tracking.", job.id)
        return

    with db_transaction.atomic():
        try:
            user_plan = UserPlan.objects.select_for_update().get(user_id=user_id)
        except UserPlan.DoesNotExist:
            logger.warning("No UserPlan for user %s, skipping usage tracking.", user_id)
            return

        # This is the actual idempotency guard. get_or_create() issues the
        # INSERT and lets the DB's unique constraint decide who wins; the
        # loser gets IntegrityError internally and Django transparently
        # re-fetches, returning created=False. No window exists where two
        # callers can both believe they're "first".
        usage_log, created = UsageLog.objects.get_or_create(
            campaign_id=str(job.id),
            action="generated",
            defaults={
                "user_id": user_id,
                "metadata": {"plan": user_plan.plan.plan_type},
            },
        )

        if not created:
            logger.info(
                "Usage already tracked for job %s (user %s) — skipping duplicate increment.",
                job.id, user_id,
            )
            return

        user_plan.campaigns_used += 1
        user_plan.campaigns_generated += 1
        user_plan.daily_generation_count += 1
        user_plan.last_generation_date = timezone.now().date()
        user_plan.save()

    logger.info("Usage tracked for job %s (user %s).", job.id, user_id)
    
def apply_render_result(job, *, success: bool, video_url: str = "", error: str = "") -> None:
    """
    Applies the result received from the GitHub Actions callback.
    On success: downloads the video, saves it to the job, marks it
    completed, and increments the user's usage counters server-side.
    On failure: marks the job failed with the given error.
    """
    if not success:
        job.status = "failed"
        job.stage = "video_render_failed"
        job.error = error or "GitHub Actions render failed"
        job.save(update_fields=["status", "stage", "error"])
        return

    if not video_url:
        job.status = "failed"
        job.stage = "video_render_failed"
        job.error = "Render reported success but no video_url was provided"
        job.save(update_fields=["status", "stage", "error"])
        return

    resp = requests.get(video_url, timeout=60)
    resp.raise_for_status()

    job.video.save(f"{job.id}.mp4", ContentFile(resp.content), save=False)
    job.status = "completed"
    job.stage = "completed"
    job.error = None
    job.save(update_fields=["video", "status", "stage", "error"])

    _track_usage(job)