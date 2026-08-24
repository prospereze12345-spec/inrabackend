import hmac
import json
import logging
import os
import uuid

import requests
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AIJob, PreviewRenderJob
from .promo import apply_render_result, dispatch_preview_render
from .services.qstash_client import enqueue_ai_job
from .services.renderer import SOCIAL_FORMATS, normalize_promo_props


logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS
# ============================================================================

def _find_job(job_id):
    """
    Find a job by ID across AIJob and PreviewRenderJob.

    Returns:
        (job, "aijob")
        (job, "preview")
        (None, None)
    """
    try:
        return AIJob.objects.get(id=job_id), "aijob"
    except AIJob.DoesNotExist:
        pass

    try:
        return PreviewRenderJob.objects.get(id=job_id), "preview"
    except PreviewRenderJob.DoesNotExist:
        return None, None


def _get_job_status(status_value):
    """
    Normalize internal job statuses to the public API statuses
    expected by the frontend.
    """
    return {
        "pending": "pending",
        "processing": "processing",
        "completed": "done",
        "done": "done",
        "failed": "error",
        "error": "error",
    }.get(status_value, "pending")


def _serialize_file_value(value, request=None):
    """
    Convert Django FileField/ImageField values into usable URLs.

    This prevents DRF responses from accidentally exposing FileField
    objects instead of strings.
    """
    if not value:
        return ""

    if hasattr(value, "url"):
        try:
            url = value.url

            if request and url and not url.startswith(("http://", "https://")):
                return request.build_absolute_uri(url)

            return url
        except ValueError:
            return ""

    return value


# ============================================================================
# CREATE AI JOB
# ============================================================================

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

        job = AIJob.objects.create(
            image=image,
            user=request.user,
        )

        try:
            enqueue_ai_job(str(job.id))

        except Exception:
            logger.exception(
                "Failed to enqueue AI job %s",
                job.id,
            )

            update_fields = []

            if hasattr(job, "status"):
                job.status = "failed"
                update_fields.append("status")

            if hasattr(job, "error"):
                job.error = "Failed to enqueue AI job."
                update_fields.append("error")

            if update_fields:
                job.save(update_fields=update_fields)

            return Response(
                {"error": "Failed to enqueue AI job."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ============================================================================
# JOB STATUS
# ============================================================================

class JobStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, job_id):
        job, job_kind = _find_job(job_id)

        if job is None:
            logger.warning(
                "JobStatusView: no job found for id=%s",
                job_id,
            )

            return Response(
                {"error": "job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        response = {
            "job_id": str(job.id),
            "status": _get_job_status(job.status),
            "job_type": job_kind,
        }

        if hasattr(job, "stage"):
            response["stage"] = job.stage or ""

        if hasattr(job, "error"):
            response["error"] = job.error or ""

        if hasattr(job, "video_url"):
            response["video_url"] = _serialize_file_value(
                job.video_url,
                request,
            )

        return Response(
            response,
            status=status.HTTP_200_OK,
        )


# ============================================================================
# JOB RESULT
# ============================================================================

class JobResultView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, job_id):
        job, job_kind = _find_job(job_id)

        if job is None:
            logger.warning(
                "JobResultView: no job found for id=%s",
                job_id,
            )

            return Response(
                {"error": "job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        current_status = _get_job_status(job.status)

        if current_status != "done":
            return Response(
                {
                    "job_id": str(job.id),
                    "job_type": job_kind,
                    "status": current_status,
                    "result": None,
                },
                status=status.HTTP_200_OK,
            )

        result = {}

        result_fields = (
            "video_url",
            "image_url",
            "image_nobg",
            "caption",
            "result",
            "output",
        )

        for field_name in result_fields:
            if not hasattr(job, field_name):
                continue

            value = getattr(job, field_name)

            if value in (None, ""):
                continue

            if field_name in {
                "video_url",
                "image_url",
                "image_nobg",
            }:
                value = _serialize_file_value(
                    value,
                    request,
                )

            result[field_name] = value

        return Response(
            {
                "job_id": str(job.id),
                "job_type": job_kind,
                "status": "done",
                "result": result,
            },
            status=status.HTTP_200_OK,
        )


# ============================================================================
# RECENT CAMPAIGNS
# ============================================================================

class RecentCampaignsView(APIView):
    """
    Return recent campaigns for the authenticated user.

    IMPORTANT:
    This endpoint intentionally returns the campaigns ARRAY directly.

    The frontend currently expects:

        recentCampaigns.slice(...)

    Therefore the response must be:

        [
            {...},
            {...}
        ]

    and NOT:

        {
            "campaigns": [...],
            "count": 1
        }

    Changing the response to an object causes:
        TypeError: ec.slice is not a function
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit_param = request.query_params.get("limit", "10")

        try:
            limit = int(limit_param)
        except (TypeError, ValueError):
            limit = 10

        # Protect the endpoint from unreasonable values.
        limit = max(1, min(limit, 50))

        queryset = AIJob.objects.filter(
            user=request.user
        )

        # Determine the available timestamp field without assuming
        # a specific model implementation.
        field_names = {
            field.name
            for field in AIJob._meta.get_fields()
        }

        if "created_at" in field_names:
            queryset = queryset.order_by("-created_at")

        elif "created" in field_names:
            queryset = queryset.order_by("-created")

        elif "updated_at" in field_names:
            queryset = queryset.order_by("-updated_at")

        elif "updated" in field_names:
            queryset = queryset.order_by("-updated")

        jobs = queryset[:limit]

        campaigns = []

        for job in jobs:
            campaign = {
                "job_id": str(job.id),
                "status": _get_job_status(
                    getattr(job, "status", "pending")
                ),
            }

            # Optional campaign fields.
            for field_name in (
                "stage",
                "caption",
                "error",
            ):
                if hasattr(job, field_name):
                    value = getattr(job, field_name)

                    if value is not None:
                        campaign[field_name] = value

            # File/image/video fields.
            for field_name in (
                "video_url",
                "image_url",
                "image_nobg",
            ):
                if hasattr(job, field_name):
                    value = getattr(job, field_name)

                    campaign[field_name] = _serialize_file_value(
                        value,
                        request,
                    )

            # Timestamp fields.
            for field_name in (
                "created_at",
                "created",
                "updated_at",
                "updated",
            ):
                if hasattr(job, field_name):
                    value = getattr(job, field_name)

                    if value is not None:
                        campaign[field_name] = value.isoformat()

            campaigns.append(campaign)

        # IMPORTANT:
        # Return the ARRAY directly.
        #
        # Frontend expects:
        # recentCampaigns.slice(...)
        #
        # Do NOT return:
        # {"campaigns": campaigns, "count": len(campaigns)}
        return Response(
            campaigns,
            status=status.HTTP_200_OK,
        )


# ============================================================================
# ASSET UPLOAD
# ============================================================================

@csrf_exempt
@require_POST
def upload_asset(request):
    file = request.FILES.get("file")

    if not file:
        return JsonResponse(
            {"error": "No file provided"},
            status=400,
        )

    extension = os.path.splitext(file.name)[1].lower()

    filename = (
        f"uploads/{uuid.uuid4().hex}{extension}"
    )

    try:
        saved_path = default_storage.save(
            filename,
            file,
        )

        raw_url = default_storage.url(
            saved_path
        )

    except Exception:
        logger.exception(
            "Failed to save uploaded asset"
        )

        return JsonResponse(
            {"error": "Failed to save file."},
            status=500,
        )

    if raw_url.startswith(("http://", "https://")):
        file_url = raw_url
    else:
        file_url = request.build_absolute_uri(
            raw_url
        )

    return JsonResponse(
        {
            "url": file_url,
        },
        status=200,
    )


# ============================================================================
# VIDEO RENDER DISPATCH
# ============================================================================

@csrf_exempt
@require_POST
def render_video_view(request):
    """
    Dispatch an editor-preview video render.

    The request returns immediately with a PreviewRenderJob ID.
    The frontend polls JobStatusView for completion.
    """

    try:
        payload = json.loads(
            request.body.decode("utf-8")
        )

    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON body."},
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {"error": "JSON body must be an object."},
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
                    f"Available: "
                    f"{list(SOCIAL_FORMATS.keys())}"
                )
            },
            status=400,
        )

    try:
        props = normalize_promo_props(
            payload.get("props")
        )

    except Exception:
        logger.exception(
            "Failed to normalize render props"
        )

        return JsonResponse(
            {"error": "Invalid render properties."},
            status=400,
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
        logger.exception(
            "Render dispatch failed for preview job %s",
            job.id,
        )

        job.status = "failed"

        update_fields = ["status"]

        if hasattr(job, "error"):
            job.error = str(exc)
            update_fields.append("error")

        job.save(
            update_fields=update_fields
        )

        return JsonResponse(
            {
                "error": "Render dispatch failed.",
                "detail": str(exc),
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


# ============================================================================
# VIDEO RENDER CALLBACK
# ============================================================================

@csrf_exempt
@require_POST
def video_render_complete(request):
    expected_secret = getattr(
        settings,
        "RENDER_CALLBACK_SECRET",
        "",
    )

    provided_secret = request.headers.get(
        "X-Callback-Secret",
        "",
    )

    if (
        not expected_secret
        or not hmac.compare_digest(
            provided_secret,
            expected_secret,
        )
    ):
        logger.warning(
            "Unauthorized render callback received"
        )

        return JsonResponse(
            {"error": "unauthorized"},
            status=401,
        )

    try:
        data = json.loads(
            request.body.decode("utf-8")
        )

    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "bad request"},
            status=400,
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "bad request"},
            status=400,
        )

    job_id = data.get("job_id")
    render_status = data.get("status")

    if not job_id or not render_status:
        return JsonResponse(
            {
                "error": (
                    "job_id and status are required"
                )
            },
            status=400,
        )

    job, job_kind = _find_job(job_id)

    if job is None:
        logger.warning(
            "video_render_complete: "
            "no job found for id=%s",
            job_id,
        )

        return JsonResponse(
            {"error": "job not found"},
            status=404,
        )

    # ------------------------------------------------------------------------
    # AIJob
    # ------------------------------------------------------------------------

    if job_kind == "aijob":
        try:
            apply_render_result(
                job,
                success=(
                    render_status == "success"
                ),
                video_url=data.get(
                    "video_url",
                    "",
                ),
                error=data.get(
                    "error",
                    "",
                ),
            )

        except requests.RequestException as exc:
            logger.exception(
                "Failed to fetch rendered video "
                "for job %s",
                job_id,
            )

            job.status = "failed"

            update_fields = ["status"]

            if hasattr(job, "stage"):
                job.stage = "video_render_failed"
                update_fields.append("stage")

            if hasattr(job, "error"):
                job.error = (
                    "Failed to fetch rendered "
                    f"video: {exc}"
                )
                update_fields.append("error")

            job.save(
                update_fields=update_fields
            )

            return JsonResponse(
                {"error": "fetch failed"},
                status=502,
            )

        except Exception:
            logger.exception(
                "Failed to apply render result "
                "for job %s",
                job_id,
            )

            return JsonResponse(
                {
                    "error": (
                        "failed to apply "
                        "render result"
                    )
                },
                status=500,
            )

    # ------------------------------------------------------------------------
    # PreviewRenderJob
    # ------------------------------------------------------------------------

    else:
        job.status = (
            "completed"
            if render_status == "success"
            else "failed"
        )

        update_fields = ["status"]

        if hasattr(job, "error"):
            job.error = data.get(
                "error",
                "",
            )
            update_fields.append("error")

        if hasattr(job, "video_url"):
            job.video_url = data.get(
                "video_url",
                "",
            )
            update_fields.append("video_url")

        job.save(
            update_fields=update_fields
        )

    return JsonResponse(
        {"ok": True},
        status=200,
    )