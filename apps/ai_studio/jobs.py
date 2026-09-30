"""
apps/ai_studio/jobs.py

QStash-backed AI campaign pipeline.

This replaces the old Celery task implementation.

QStash retry behavior
---------------------
Transient failure:
    raise RetryableJobError(exc)
        -> webhook returns 5xx
        -> QStash redelivers the request

Permanent failure:
    raise NonRetryableJobError(exc)
        -> webhook returns the configured non-retryable response
        -> QStash stops retrying and moves the message to the DLQ

IMPORTANT
---------
This file NEVER consumes Free/PAYG/Pro entitlement.

Entitlement accounting is handled only after a campaign successfully
completes in apps.ai_studio.promo._track_usage().

Therefore:

    generation starts
        -> entitlement checked
        -> AI pipeline runs
        -> failure
        -> NO usage charged

    generation succeeds
        -> final render completes
        -> promo._track_usage()
        -> entitlement consumed exactly once
"""

import logging
import os
import tempfile

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import AIJob
from .services.background_removal import remove_background_from_bytes
from .services.captions import (
    CaptionGenerationError,
    generate_captions,
)
from .services.flyer_generator import build_flyer
from .services.image_understanding import (
    ImageAnalysisError,
    analyze_image,
)
from .services.product_parser import build_product_context
from .services.video_generator import dispatch_job_video


logger = logging.getLogger(__name__)


class RetryableJobError(Exception):
    """
    Transient failure.

    QStash should redeliver the webhook.
    """


class NonRetryableJobError(Exception):
    """
    Permanent failure.

    Retrying the same request will not fix the problem.
    """


def _set_stage(job: "AIJob", stage: str) -> None:
    """
    Persist the current AI pipeline stage.
    """
    job.stage = stage
    job.save(update_fields=["stage"])

    logger.info(
        "Job %s → %s",
        job.id,
        stage,
    )


def _fail(job: "AIJob", error: Exception) -> None:
    """
    Mark the job as failed.

    This does NOT consume or modify user entitlement.
    """
    job.status = "failed"
    job.error = f"[{job.stage}] {error}"

    job.save(
        update_fields=[
            "status",
            "error",
        ]
    )

    logger.error(
        "Job %s failed at stage=%s: %s",
        job.id,
        job.stage,
        error,
    )


def run_ai_job(job_id: str) -> None:
    """
    Run the complete AI campaign pipeline.

    Pipeline:

        image
          ↓
        background removal
          ↓
        image analysis
          ↓
        product context
          ↓
        captions
          ↓
        flyer
          ↓
        GitHub Actions video render
          ↓
        video callback
          ↓
        completed campaign
          ↓
        usage accounting

    IMPORTANT:
    Usage is NOT consumed here.

    The campaign is only considered successfully generated when the final
    video render callback completes the AIJob. promo.py then records usage.
    """

    # ------------------------------------------------------------------
    # FETCH JOB
    # ------------------------------------------------------------------
    try:
        job = AIJob.objects.get(id=job_id)

    except AIJob.DoesNotExist:
        logger.error(
            "run_ai_job called with unknown job_id=%s",
            job_id,
        )

        raise NonRetryableJobError(
            f"No AIJob with id={job_id}"
        )

    # ------------------------------------------------------------------
    # IDEMPOTENCY GUARD
    # ------------------------------------------------------------------
    #
    # QStash can redeliver requests.
    #
    # If the final campaign has already completed, NEVER restart the
    # entire AI pipeline.
    #
    # This protects against duplicate Gemini calls, duplicate flyer
    # generation, and duplicate video dispatches after a repeated webhook.
    if job.status == "completed":
        logger.info(
            "Job %s is already completed. Skipping duplicate execution.",
            job.id,
        )
        return

    # If the video render has already been dispatched, do not restart the
    # entire AI pipeline. The GitHub Actions callback is responsible for
    # completing the job.
    #
    # This is particularly important if the QStash request is delivered
    # again after the render dispatch already succeeded.
    if (
        job.stage == "rendering_video"
        and job.status == "processing"
    ):
        logger.info(
            "Job %s is already waiting for video render completion. "
            "Skipping duplicate AI pipeline execution.",
            job.id,
        )
        return

    # ------------------------------------------------------------------
    # START / RESUME PROCESSING
    # ------------------------------------------------------------------
    job.status = "processing"
    job.error = None

    job.save(
        update_fields=[
            "status",
            "error",
        ]
    )

    # ------------------------------------------------------------------
    # STAGE 1: BACKGROUND REMOVAL
    # ------------------------------------------------------------------
    try:
        _set_stage(
            job,
            "removing_background",
        )

        with job.image.open("rb") as fh:
            raw_bytes = fh.read()

        png_bytes = remove_background_from_bytes(
            raw_bytes
        )

        png_filename = f"{job.id}_nobg.png"

        job.image_nobg.save(
            png_filename,
            ContentFile(png_bytes),
            save=True,
        )

        image_bytes = png_bytes

    except Exception as exc:
        _fail(
            job,
            exc,
        )

        # Background removal failures are generally treated as transient
        # because the underlying provider/network may recover.
        raise RetryableJobError(exc) from exc

    # ------------------------------------------------------------------
    # STAGE 2: AI IMAGE ANALYSIS
    # ------------------------------------------------------------------
    try:
        _set_stage(
            job,
            "analyzing_image",
        )

        analysis = analyze_image(
            image_bytes
        )

    except ImageAnalysisError as exc:
        _fail(
            job,
            exc,
        )

        if exc.is_retryable:
            raise RetryableJobError(exc) from exc

        raise NonRetryableJobError(exc) from exc

    # ------------------------------------------------------------------
    # STAGE 3: PRODUCT CONTEXT
    # ------------------------------------------------------------------
    try:
        _set_stage(
            job,
            "building_product_context",
        )

        product = build_product_context(
            analysis
        )

    except Exception as exc:
        _fail(
            job,
            exc,
        )

        raise NonRetryableJobError(exc) from exc

    # ------------------------------------------------------------------
    # STAGE 4: CAPTIONS
    # ------------------------------------------------------------------
    try:
        _set_stage(
            job,
            "generating_captions",
        )

        captions = generate_captions(
            product
        )

        job.captions = captions

        job.save(
            update_fields=[
                "captions",
            ]
        )

    except CaptionGenerationError as exc:
        _fail(
            job,
            exc,
        )

        if exc.is_retryable:
            raise RetryableJobError(exc) from exc

        raise NonRetryableJobError(exc) from exc

    # ------------------------------------------------------------------
    # STAGE 5: FLYER
    # ------------------------------------------------------------------
    try:
        _set_stage(
            job,
            "building_flyer",
        )

        # Retrieve the background-removed image through the configured
        # storage backend. This works with local storage, Cloudinary,
        # S3-compatible storage, etc.
        with default_storage.open(
            job.image_nobg.name,
            "rb",
        ) as remote_file:

            with tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False,
            ) as tmp:
                tmp.write(
                    remote_file.read()
                )

                nobg_abs = tmp.name

        flyer_abs = os.path.join(
            settings.MEDIA_ROOT,
            "flyers",
            f"{job.id}.jpg",
        )

        os.makedirs(
            os.path.dirname(flyer_abs),
            exist_ok=True,
        )

        try:
            flyer_result = build_flyer(
                captions,
                nobg_abs,
                flyer_abs,
            )

        finally:
            # Always remove the temporary local file, even when flyer
            # generation itself raises an exception.
            try:
                os.remove(nobg_abs)
            except FileNotFoundError:
                pass

        job.flyer = (
            f"flyers/{job.id}.jpg"
        )

        job.flyer_props = (
            flyer_result["props"]
        )

        job.save(
            update_fields=[
                "flyer",
                "flyer_props",
            ]
        )

    except Exception as exc:
        _fail(
            job,
            exc,
        )

        # Preserve the existing behavior: flyer-generation failures are
        # treated as retryable.
        raise RetryableJobError(exc) from exc

    # ------------------------------------------------------------------
    # STAGE 6: VIDEO RENDER DISPATCH
    # ------------------------------------------------------------------
    try:
        _set_stage(
            job,
            "generating_video",
        )

        # Do NOT render Remotion on the Django/Render server.
        #
        # GitHub Actions performs the actual video render and calls
        # video_render_complete() when finished.
        dispatch_job_video(
            job
        )

        # dispatch_job_video() changes the job stage to rendering_video
        # when the GitHub render is successfully dispatched.
        logger.info(
            "Job %s video render dispatched to GitHub Actions.",
            job.id,
        )

    except Exception as exc:
        _fail(
            job,
            exc,
        )

        # Dispatch failures are retryable because GitHub Actions/network
        # availability can recover.
        raise RetryableJobError(exc) from exc

    # ------------------------------------------------------------------
    # IMPORTANT
    # ------------------------------------------------------------------
    #
    # We do NOT mark the job completed here.
    #
    # The video still has to be rendered by GitHub Actions.
    #
    # The callback in views.py:
    #
    #     video_render_complete()
    #
    # calls:
    #
    #     apply_render_result()
    #
    # which marks the AIJob completed and then calls:
    #
    #     _track_usage()
    #
    # That is the single authoritative successful-generation accounting
    # path.
    logger.info(
        "Job %s AI pipeline reached video rendering successfully. "
        "Waiting for GitHub Actions callback.",
        job.id,
    )
