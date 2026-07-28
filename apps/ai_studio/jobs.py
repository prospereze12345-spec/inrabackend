"""
Replaces tasks.py.

This is now a plain function, not a @shared_task. It is invoked by the
QStash webhook view (webhooks.py), not by a Celery worker. All the stage
logic is unchanged from the original file — only the retry mechanics differ:

    Celery:  raise self.retry(exc=exc)         → broker redelivers to a worker
    QStash:  raise RetryableJobError(exc)        → webhook returns 5xx → QStash
                                                    redelivers the HTTP request

    Celery:  raise (no retry)                  → task marked FAILURE
    QStash:  raise NonRetryableJobError(exc)     → webhook returns 489 with
                                                    Upstash-NonRetryable-Error
                                                    → QStash stops immediately
                                                    and moves the message to
                                                    the Dead Letter Queue
"""
import os
import logging

from django.conf import settings
from django.core.files.base import ContentFile

from .models import AIJob
from .services.background_removal import remove_background_from_bytes
from .services.image_understanding import analyze_image, ImageAnalysisError
from .services.product_parser import build_product_context
from .services.captions import generate_captions, CaptionGenerationError
from .services.flyer_generator import build_flyer
from .services.video_generator import ensure_job_video

logger = logging.getLogger(__name__)


class RetryableJobError(Exception):
    """Transient failure (network/API blip) — safe for QStash to redeliver."""


class NonRetryableJobError(Exception):
    """Permanent failure (bad data, parse error) — redelivery won't help."""


def _set_stage(job: "AIJob", stage: str) -> None:
    job.stage = stage
    job.save(update_fields=["stage"])
    logger.info("Job %s → %s", job.id, stage)


def _fail(job: "AIJob", error: Exception) -> None:
    job.status = "failed"
    job.error = f"[{job.stage}] {error}"
    job.save(update_fields=["status", "error"])
    logger.error("Job %s failed at stage=%s: %s", job.id, job.stage, error)


def run_ai_job(job_id: str) -> None:
    """
    Full AI pipeline for a single job:
        image → background removal → analysis → product context →
        captions → flyer → video

    Called synchronously from the QStash webhook. Raises RetryableJobError
    or NonRetryableJobError so the webhook can pick the right HTTP status
    code to send back to QStash.
    """
    # ── fetch job ─────────────────────────────────────────────────────────
    try:
        job = AIJob.objects.get(id=job_id)
    except AIJob.DoesNotExist:
        logger.error("run_ai_job called with unknown job_id=%s", job_id)
        raise NonRetryableJobError(f"No AIJob with id={job_id}")

    job.status = "processing"
    job.stage = "starting"
    job.save(update_fields=["status", "stage"])

    # ── stage 1: background removal ─────────────────────────────────────────
    try:
        _set_stage(job, "removing_background")
        with job.image.open("rb") as fh:
            raw_bytes = fh.read()

        png_bytes = remove_background_from_bytes(raw_bytes)

        png_filename = f"{job.id}_nobg.png"
        job.image_nobg.save(png_filename, ContentFile(png_bytes), save=True)

        image_bytes = png_bytes
    except Exception as exc:
        _fail(job, exc)
        # Background removal failures are usually transient API issues.
        raise RetryableJobError(exc) from exc

    # ── stage 2: AI image analysis ───────────────────────────────────────────
    try:
        _set_stage(job, "analyzing_image")
        analysis = analyze_image(image_bytes)
    except ImageAnalysisError as exc:
        _fail(job, exc)
        if exc.is_retryable:
            raise RetryableJobError(exc) from exc
        raise NonRetryableJobError(exc) from exc

    # ── stage 3: build product context ──────────────────────────────────────
    try:
        _set_stage(job, "building_product_context")
        product = build_product_context(analysis)
    except Exception as exc:
        _fail(job, exc)
        raise NonRetryableJobError(exc) from exc

    # ── stage 4: generate captions ───────────────────────────────────────────
    try:
        _set_stage(job, "generating_captions")
        captions = generate_captions(product)
        job.captions = captions
        job.save(update_fields=["captions"])
    except CaptionGenerationError as exc:
        _fail(job, exc)
        if exc.is_retryable:
            raise RetryableJobError(exc) from exc
        raise NonRetryableJobError(exc) from exc

    # ── stage 5: build flyer ─────────────────────────────────────────────────
    try:
        _set_stage(job, "building_flyer")

        nobg_abs = os.path.join(settings.MEDIA_ROOT, str(job.image_nobg.name))
        flyer_abs = os.path.join(settings.MEDIA_ROOT, "flyers", f"{job.id}.jpg")

        flyer_result = build_flyer(captions, nobg_abs, flyer_abs)

        job.flyer = f"flyers/{job.id}.jpg"
        job.flyer_props = flyer_result["props"]
        job.save(update_fields=["flyer", "flyer_props"])
    except Exception as exc:
        _fail(job, exc)
        raise RetryableJobError(exc) from exc

    # ── stage 6: generate video ───────────────────────────────────────────────
    try:
        _set_stage(job, "generating_video")
        ensure_job_video(job, verbose=True)
    except Exception as exc:
        _fail(job, exc)
        raise RetryableJobError(exc) from exc

    job.status = "completed"
    job.stage = "done"
    job.save(update_fields=["status", "stage"])
    logger.info("Job %s completed successfully", job.id)
