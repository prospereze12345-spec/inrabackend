import os
import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from celery import shared_task

from .models import AIJob
from .services.background_removal import remove_background_from_bytes
from .services.image_understanding import analyze_image, ImageAnalysisError
from .services.product_parser import build_product_context
from .services.captions import generate_captions, CaptionGenerationError
from .services.flyer_generator import build_flyer
from .services.video_generator import ensure_job_video
logger = logging.getLogger(__name__)


def _set_stage(job: "AIJob", stage: str) -> None:
    """Checkpoint progress so failed jobs show exactly where they died."""
    job.stage = stage
    job.save(update_fields=["stage"])
    logger.info("Job %s → %s", job.id, stage)


def _fail(job: "AIJob", error: Exception) -> None:
    job.status = "failed"
    job.error  = f"[{job.stage}] {error}"
    job.save(update_fields=["status", "error"])
    logger.error("Job %s failed at stage=%s: %s", job.id, job.stage, error)
# ── task ──────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,    # seconds between retries
    acks_late=True,            # only ack after task completes — safe on worker crash
)
def process_ai_job(self, job_id: str) -> None:
    """
    Full AI pipeline for a single job:
        image → analysis → product context → captions → flyer → video

    Retry behavior:
        - Network/API transient errors  → retried (up to max_retries)
        - Parse errors / bad data       → fail immediately, no retry
        - Missing job                   → fail immediately, no retry
    """

    # ── fetch job ─────────────────────────────────────────────────────────────
    try:
        job = AIJob.objects.get(id=job_id)
    except AIJob.DoesNotExist:
        # No point retrying — the job record is genuinely gone
        logger.error("process_ai_job called with unknown job_id=%s", job_id)
        return

    job.status = "processing"
    job.stage  = "starting"
    job.save(update_fields=["status", "stage"])

    try:
        _set_stage(job, "removing_background")
        with job.image.open("rb") as fh:
            raw_bytes = fh.read()

        # Remove background → get transparent PNG bytes
        png_bytes = remove_background_from_bytes(raw_bytes)

        # Save the bg-removed PNG back onto the job
        from django.core.files.base import ContentFile
        png_filename = f"{job.id}_nobg.png"
        job.image_nobg.save(png_filename, ContentFile(png_bytes), save=True)

        # Pass PNG bytes downstream to the analyzer
        image_bytes = png_bytes

    except Exception as exc:
       _fail(job, exc)
       raise

    # ── stage 2: AI image analysis ────────────────────────────────────────────
    try:
        _set_stage(job, "analyzing_image")
        analysis = analyze_image(image_bytes)
    except ImageAnalysisError as exc:
        _fail(job, exc)
        if exc.is_retryable:
            raise self.retry(exc=exc)
        raise

    

    # ── stage 3: build product context ────────────────────────────────────────
    try:
        _set_stage(job, "building_product_context")
        product = build_product_context(analysis)
    except Exception as exc:
        _fail(job, exc)
        raise

    # ── stage 4: generate captions ────────────────────────────────────────────
    try:
        _set_stage(job, "generating_captions")
        captions = generate_captions(product)   # dict, not json.dumps(product)
        job.captions = captions
        job.save(update_fields=["captions"])
    except CaptionGenerationError as exc:
        _fail(job, exc)
        if exc.is_retryable:
            raise self.retry(exc=exc)
        raise

    # ── stage 5: build flyer ──────────────────────────────────────────────────
    try:
        _set_stage(job, "building_flyer")

        nobg_abs  = os.path.join(settings.MEDIA_ROOT, str(job.image_nobg.name))
        flyer_abs = os.path.join(settings.MEDIA_ROOT, "flyers", f"{job.id}.jpg")

        flyer_result = build_flyer(captions, nobg_abs, flyer_abs)  # ✅ nobg, not job.image

        job.flyer       = f"flyers/{job.id}.jpg"
        job.flyer_props = flyer_result["props"]
        job.save(update_fields=["flyer", "flyer_props"])
    except Exception as exc:
        _fail(job, exc)
        raise

## ── stage 6: generate video ──────────────────────────────────────────────
    try:
        _set_stage(job, "generating_video")
        ensure_job_video(job, verbose=True)
    except Exception as exc:
      _fail(job, exc)
      raise
    job.status = "completed"
    job.stage  = "done"
    job.save(update_fields=["status", "stage"])
    logger.info("Job %s completed successfully", job.id)