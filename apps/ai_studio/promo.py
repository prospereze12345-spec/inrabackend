
import logging
from typing import Any, Dict

from django.conf import settings
from django.core.files.storage import default_storage
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

    # Try to use existing promo props stored on the job.
    raw_props = getattr(job, "promo_props", None)

    if raw_props is None:
        raw_props = getattr(job, "promoProps", None)

    if raw_props is None:
        raw_props = {}

    if not isinstance(raw_props, dict):
        raw_props = {}

    props: Dict[str, Any] = dict(raw_props)

    # Fill missing values from common job fields.
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

    possible_fields = (
        "format_name",
        "video_format",
        "format",
        "aspect_ratio",
    )

    format_name = None

    for field_name in possible_fields:
        value = getattr(job, field_name, None)

        if value:
            format_name = str(value).lower().strip()
            break

    if not format_name:
        format_name = "ig"

    # Only allow formats that actually exist in SOCIAL_FORMATS.
    if format_name not in SOCIAL_FORMATS:
        logger.warning(
            "Unknown video format '%s' for job %s. Falling back to 'ig'.",
            format_name,
            job.id,
        )
        format_name = "ig"

    return format_name


def dispatch_job_video(job) -> None:
    """
    Dispatch a video-rendering job to GitHub Actions.

    Django creates the render configuration and sends it to GitHub.
    GitHub Actions performs the actual Remotion render, uploads the MP4
    to Cloudinary, and calls the Django callback when finished.
    """

    # Don't render again if a video already exists.
    if job.video and default_storage.exists(job.video.name):
        logger.info(
            "Job %s already has a rendered video. Skipping.",
            job.id,
        )
        return

    props = build_promo_props(job)

    format_name = resolve_video_format(job)
    format_config = SOCIAL_FORMATS[format_name]

    config = {
        "compositionId": "PromoVideo",
        "inputProps": props,
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

    # Mark the job as rendering before contacting GitHub.
    job.stage = "rendering_video"
    job.status = "processing"
    job.save(update_fields=["stage", "status"])

    try:
        trigger_github_render(
            job_id=str(job.id),
            config=config,
        )

        logger.info(
            "GitHub Actions render dispatched successfully for job %s.",
            job.id,
        )

    except Exception as exc:
        logger.exception(
            "Failed to dispatch GitHub render for job %s.",
            job.id,
        )

        job.status = "failed"
        job.stage = "video_dispatch_failed"
        job.error = str(exc)

        job.save(
            update_fields=[
                "status",
                "stage",
                "error",
            ]
        )

        raise


def dispatch_preview_render(job, *, props: dict, format_name: str) -> None:
    """
    Like dispatch_job_video, but for one-off editor-preview exports where
    props are supplied directly by the caller rather than built from a
    persisted AIJob's fields.
    """
    format_config = SOCIAL_FORMATS[format_name]

    config = {
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


import requests
from django.core.files.base import ContentFile

def apply_render_result(job, *, success: bool, video_url: str = "", error: str = "") -> None:
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