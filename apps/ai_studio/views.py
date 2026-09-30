
import hmac
import json
import logging
import os
import uuid

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pricing.models import UserPlan
from apps.pricing.services.entitlement import get_entitlement

from .models import AIJob, PreviewRenderJob
from .promo import (
    apply_preview_render_result,
    apply_render_result,
    dispatch_preview_render,
)
from .services.qstash_client import enqueue_ai_job
from .services.renderer import SOCIAL_FORMATS, normalize_promo_props


logger = logging.getLogger(__name__)


class CreateAIJobView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        image = request.FILES.get("image")

        if not image:
            return Response(
                {"error": "Image required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # IMPORTANT:
        # This endpoint CHECKS entitlement but does not permanently consume it.
        #
        # A generation is only charged after the AI campaign actually
        # completes successfully. This prevents Gemini/QStash/provider
        # failures from consuming the user's Free/PAYG/Pro entitlement.
        try:
            user_plan = (
                UserPlan.objects
                .select_related("plan")
                .get(user=request.user)
            )
        except UserPlan.DoesNotExist:
            return Response(
                {
                    "error": "No active plan found. Visit the dashboard first.",
                    "can_generate": False,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        entitlement = get_entitlement(user_plan)

        if not entitlement["can_generate"]:
            return Response(
                {
                    "error": (
                        entitlement["message"]
                        or "No generations available."
                    ),
                    "can_generate": False,
                    "remaining": entitlement["remaining"],
                    "source": entitlement["source"],
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Create the AI job only after the entitlement check passes.
        #
        # We deliberately do NOT modify UserPlan here.
        # The successful-completion path in promo.py is now the single
        # authoritative place that records actual usage.
        try:
            job = AIJob.objects.create(
                image=image,
                user=request.user,
            )
        except Exception:
            logger.exception(
                "Failed to create AI job for user=%s",
                request.user.id,
            )
            return Response(
                {
                    "error": "Could not create generation job. Please try again."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Queue the job.
        #
        # If queueing fails, the job is marked failed and the entitlement
        # remains untouched because we have not consumed anything yet.
        try:
            enqueue_ai_job(str(job.id))
        except Exception:
            logger.exception(
                "Failed to enqueue AI job: job=%s user=%s",
                job.id,
                request.user.id,
            )

            job.status = "failed"
            job.stage = "queue_failed"
            job.save(
                update_fields=[
                    "status",
                    "stage",
                ]
            )

            return Response(
                {
                    "error": "Could not queue generation. Please try again.",
                    "can_generate": True,
                    "remaining": entitlement["remaining"],
                    "source": entitlement["source"],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "remaining": entitlement["remaining"],
                "source": entitlement["source"],
            },
            status=status.HTTP_202_ACCEPTED,
        )


class JobStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        try:
            job = AIJob.objects.get(
                id=job_id,
                user=request.user,
            )
        except AIJob.DoesNotExist:
            return Response(
                {"error": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        status_map = {
            "pending": "pending",
            "processing": "processing",
            "completed": "done",
            "failed": "error",
        }

        return Response(
            {
                "job_id": str(job.id),
                "status": status_map.get(job.status, "pending"),
            }
        )


class JobResultView(APIView):
    permission_classes = [IsAuthenticated]

    PLATFORM_MAP = {
        "instagram": "Instagram",
        "tiktok": "TikTok",
        "twitter": "Twitter",
        "facebook": "Facebook",
        "whatsapp": "WhatsApp",
    }

    def _absolute_url(self, request, file_field):
        if not file_field:
            return None

        return request.build_absolute_uri(file_field.url)

    def get(self, request, job_id):
        try:
            job = AIJob.objects.get(
                id=job_id,
                user=request.user,
            )
        except AIJob.DoesNotExist:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job.status != "completed":
            return Response(
                {
                    "job_id": str(job.id),
                    "status": job.status,
                    "error": "Job not complete",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_captions = (job.captions or {}).get("captions", {})

        captions = [
            {
                "platform": label,
                "text": raw_captions[key],
            }
            for key, label in self.PLATFORM_MAP.items()
            if raw_captions.get(key)
        ]

        flyer = {
            **(job.flyer_props or {}),
            "productImage": (
                self._absolute_url(request, job.image_nobg) or ""
            ),
        }

        video_url = None

        if job.video:
            try:
                video_url = request.build_absolute_uri(job.video.url)
            except Exception:
                video_url = str(job.video)

        return Response(
            {
                "job_id": str(job.id),
                "status": "done",
                "png_url": self._absolute_url(
                    request,
                    job.image_nobg,
                ),
                "flyer_url": self._absolute_url(
                    request,
                    job.flyer,
                ),
                "video_url": video_url,
                "captions": captions,
                "flyer": flyer,
            },
            status=status.HTTP_200_OK,
        )


class RecentCampaignsView(APIView):
    permission_classes = [IsAuthenticated]

    def _absolute_url(self, request, file_field):
        if not file_field:
            return None

        return request.build_absolute_uri(file_field.url)

    def get(self, request):
        jobs = (
            AIJob.objects
            .filter(
                user=request.user,
                status="completed",
            )
            .order_by("-created_at")[:20]
        )

        results = [
            {
                "job_id": str(job.id),
                "headline": (
                    job.flyer_props or {}
                ).get("headline"),
                "png_url": self._absolute_url(
                    request,
                    job.image_nobg,
                ),
                "template_category": (
                    job.flyer_props or {}
                ).get("templateCategory"),
                "created_at": job.created_at.isoformat(),
            }
            for job in jobs
        ]

        return Response(
            results,
            status=status.HTTP_200_OK,
        )


@csrf_exempt
def upload_asset(request):
    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405,
        )

    file = request.FILES.get("file")

    if not file:
        return JsonResponse(
            {"error": "No file provided"},
            status=400,
        )

    ext = os.path.splitext(file.name)[1]
    filename = f"uploads/{uuid.uuid4().hex}{ext}"

    saved_path = default_storage.save(
        filename,
        file,
    )

    raw_url = default_storage.url(saved_path)

    file_url = (
        raw_url
        if raw_url.startswith("http")
        else request.build_absolute_uri(raw_url)
    )

    return JsonResponse(
        {"url": file_url}
    )


@require_GET
def render_video_status(request, job_id):
    try:
        job = PreviewRenderJob.objects.get(id=job_id)
    except (
        PreviewRenderJob.DoesNotExist,
        ValueError,
        ValidationError,
    ):
        return JsonResponse(
            {"error": "job not found"},
            status=404,
        )

    return JsonResponse(
        {
            "job_id": str(job.id),
            "status": job.status,
            "video_url": job.video_url or "",
            "error": job.error or "",
        }
    )


@csrf_exempt
@require_POST
def render_video_view(request):
    """
    One-off editor-preview export.

    Dispatches to GitHub Actions and returns immediately with a job_id
    to poll — does NOT render synchronously.

    This is an editor preview and does NOT consume campaign entitlement.
    """

    try:
        payload = json.loads(
            request.body.decode("utf-8")
        )
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return JsonResponse(
            {"error": "Invalid JSON body."},
            status=400,
        )

    format_name = payload.get(
        "format",
        "ig",
    )

    if format_name not in SOCIAL_FORMATS:
        return JsonResponse(
            {
                "error": (
                    f"Unknown format '{format_name}'. "
                    f"Available: {list(SOCIAL_FORMATS.keys())}"
                )
            },
            status=400,
        )

    props = normalize_promo_props(
        payload.get("props")
    )

    job = PreviewRenderJob.objects.create(
        status="processing",
        stage="rendering_video",
    )

    try:
        dispatch_preview_render(
            job,
            props=props,
            format_name=format_name,
        )
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)

        job.save(
            update_fields=[
                "status",
                "error",
            ]
        )

        return JsonResponse(
            {
                "error": (
                    f"Render dispatch failed: {exc}"
                )
            },
            status=500,
        )

    return JsonResponse(
        {
            "job_id": str(job.id),
            "status": "processing",
        },
        status=202,
    )


@csrf_exempt
@require_POST
def video_render_complete(request):
    provided = request.headers.get(
        "X-Callback-Secret",
        "",
    )

    expected = getattr(
        settings,
        "RENDER_CALLBACK_SECRET",
        "",
    )

    if not hmac.compare_digest(
        provided,
        expected,
    ):
        return JsonResponse(
            {"error": "unauthorized"},
            status=401,
        )

    try:
        data = json.loads(
            request.body
        )

        job_id = data["job_id"]
        render_status = data["status"]

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return JsonResponse(
            {"error": "bad request"},
            status=400,
        )

    job_id = str(job_id).strip()
    render_status = str(
        render_status
    ).strip().lower()

    if not job_id:
        return JsonResponse(
            {"error": "job_id is required"},
            status=400,
        )

    if render_status not in {
        "success",
        "failed",
    }:
        return JsonResponse(
            {
                "error": (
                    "status must be 'success' or 'failed'"
                )
            },
            status=400,
        )

    video_url = str(
        data.get("video_url") or ""
    ).strip()

    error_message = str(
        data.get("error") or ""
    ).strip()

    # Campaign renders use AIJob.
    try:
        job = AIJob.objects.get(
            id=job_id
        )
    except (
        AIJob.DoesNotExist,
        ValueError,
        ValidationError,
    ):
        job = None

    if job is not None:
        try:
            apply_render_result(
                job,
                success=(
                    render_status == "success"
                ),
                video_url=video_url,
                error=error_message,
            )
        except Exception:
            logger.exception(
                "video_render_complete: failed applying AIJob result "
                "job=%s status=%s",
                job_id,
                render_status,
            )

            return JsonResponse(
                {
                    "error": (
                        "Could not apply render result"
                    )
                },
                status=500,
            )

        return JsonResponse(
            {
                "ok": True,
                "job_type": "ai",
                "job_id": job_id,
            }
        )

    # Editor-preview renders use PreviewRenderJob.
    try:
        preview_job = PreviewRenderJob.objects.get(
            id=job_id
        )
    except (
        PreviewRenderJob.DoesNotExist,
        ValueError,
        ValidationError,
    ):
        logger.warning(
            "video_render_complete: no AIJob or PreviewRenderJob "
            "with id=%s",
            job_id,
        )

        return JsonResponse(
            {"error": "job not found"},
            status=404,
        )

    try:
        apply_preview_render_result(
            preview_job,
            success=(
                render_status == "success"
            ),
            video_url=video_url,
            error=error_message,
        )
    except Exception:
        logger.exception(
            "video_render_complete: failed applying PreviewRenderJob "
            "job=%s status=%s",
            job_id,
            render_status,
        )

        return JsonResponse(
            {
                "error": (
                    "Could not apply preview render result"
                )
            },
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "job_type": "preview",
            "job_id": job_id,
        }
    )
