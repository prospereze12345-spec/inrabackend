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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_job(job_id):
    """
    Resolve a job ID against both AIJob and PreviewRenderJob.

    Returns:
        tuple[job, job_kind]
        where job_kind is either "aijob" or "preview".

    Returns:
        (None, None) if no matching job exists.
    """
    try:
        job = AIJob.objects.get(id=job_id)
        return job, "aijob"
    except AIJob.DoesNotExist:
        pass

    try:
        job = PreviewRenderJob.objects.get(id=job_id)
        return job, "preview"
    except PreviewRenderJob.DoesNotExist:
        return None, None


def _serialize_job(job, job_kind):
    """
    Convert a job model into a stable API response.

    This intentionally avoids assuming that every field exists on both
    AIJob and PreviewRenderJob.
    """
    data = {
        "job_id": str(job.id),
        "status": job.status,
    }

    if hasattr(job, "stage"):
        data["stage"] = job.stage

    if hasattr(job, "error"):
        data["error"] = job.error or ""

    if hasattr(job, "video_url"):
        data["video_url"] = job.video_url or ""

    data["job_type"] = job_kind

    return data


# ---------------------------------------------------------------------------
# AI Job Creation
# ---------------------------------------------------------------------------

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

            # The database record exists, but the background job was never
            # successfully queued. Mark it failed when the model supports it.
            if hasattr(job, "status"):
                job.status = "failed"

            if hasattr(job, "error"):
                job.error = "Failed to enqueue AI job."

            update_fields = []

            if hasattr(job, "status"):
                update_fields.append("status")

            if hasattr(job, "error"):
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


# ---------------------------------------------------------------------------
# Job Status
# ---------------------------------------------------------------------------

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

        if job_kind == "aijob":
            status_map = {
                "pending": "pending",
                "processing": "processing",
                "completed": "done",
                "failed": "error",
            }
        else:
            status_map = {
                "pending": "pending",
                "processing": "processing",
                "completed": "done",
                "failed": "error",
            }

        response = _serialize_job(job, job_kind)

        response["status"] = status_map.get(
            job.status,
            "pending",
        )

        return Response(response)


# ---------------------------------------------------------------------------
# Job Result
# ---------------------------------------------------------------------------

class JobResultView(APIView):
    """
    Return the final result for a completed job.

    The frontend can use this endpoint after JobStatusView reports
    `done`.
    """

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

        if job.status not in {"completed", "done"}:
            status_map = {
                "pending": "pending",
                "processing": "processing",
                "failed": "error",
            }

            return Response(
                {
                    "job_id": str(job.id),
                    "job_type": job_kind,
                    "status": status_map.get(
                        job.status,
                        job.status,
                    ),
                    "result": None,
                },
                status=status.HTTP_200_OK,
            )

        result = {}

        # AIJob may have different result fields depending on the current
        # model implementation. Only expose fields that actually exist.
        for field_name in (
            "video_url",
            "image_url",
            "image_nobg",
            "caption",
            "result",
            "output",
        ):
            if hasattr(job, field_name):
                value = getattr(job, field_name)

                if value not in (None, ""):
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


# ---------------------------------------------------------------------------
# Recent Campaigns
# ---------------------------------------------------------------------------

class RecentCampaignsView(APIView):
    """
    Return recent AI jobs for the authenticated user.

    This endpoint is intentionally defensive so it continues to work even
    if the model does not contain every optional field.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = request.query_params.get("limit", "10")

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10

        limit = max(1, min(limit, 50))

        queryset = AIJob.objects.filter(
            user=request.user
        )

        if hasattr(AIJob, "_meta"):
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
            item = {
                "job_id": str(job.id),
                "status": getattr(job, "status", "pending"),
            }

            for field_name in (
                "stage",
                "video_url",
                "image_url",
                "caption",
                "error",
            ):
                if hasattr(job, field_name):
                    value = getattr(job, field_name)

                    if hasattr(value, "url"):
                        value = value.url

                    item[field_name] = value or ""

            for field_name in (
                "created_at",
                "created",
                "updated_at",
                "updated",
            ):
                if hasattr(job, field_name):
                    value = getattr(job, field_name)

                    if value is not None:
                        item[field_name] = value.isoformat()

            campaigns.append(item)

        return Response(
            {
                "campaigns": campaigns,
                "count": len(campaigns),
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Asset Upload
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def upload_asset(request):
    file = request.FILES.get("file")

    if not file:
        return JsonResponse(
            {"error": "No file provided"},
            status=400,
        )

    ext = os.path.splitext(file.name)[1].lower()

    filename = f"uploads/{uuid.uuid4().hex}{ext}"

    saved_path = default_storage.save(
        filename,
        file,
    )

    raw_url = default_storage.url(saved_path)

    if raw_url.startswith(("http://", "https://")):
        file_url = raw_url
    else:
        file_url = request.build_absolute_uri(raw_url)

    return JsonResponse(
        {
            "url": file_url,
        }
    )


# ---------------------------------------------------------------------------
# Video Render Dispatch
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def render_video_view(request):
    """
    One-off editor-preview export.

    Dispatches the render job and immediately returns a job ID that the
    frontend can poll through JobStatusView.
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

    format_name = payload.get("format", "ig")

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

        if hasattr(job, "error"):
            job.error = str(exc)
            job.save(
                update_fields=[
                    "status",
                    "error",
                ]
            )
        else:
            job.save(
                update_fields=["status"]
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


# ---------------------------------------------------------------------------
# Video Render Callback
# ---------------------------------------------------------------------------

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

    if not expected_secret or not hmac.compare_digest(
        provided_secret,
        expected_secret,
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
                "error": "job_id and status are required"
            },
            status=400,
        )

    job, job_kind = _find_job(job_id)

    if job is None:
        logger.warning(
            "video_render_complete: no job found for id=%s",
            job_id,
        )

        return JsonResponse(
            {"error": "job not found"},
            status=404,
        )

    if job_kind == "aijob":
        try:
            apply_render_result(
                job,
                success=(render_status == "success"),
                video_url=data.get("video_url", ""),
                error=data.get("error", ""),
            )

        except requests.RequestException as exc:
            logger.exception(
                "Failed to fetch rendered video for job %s",
                job_id,
            )

            job.status = "failed"

            if hasattr(job, "stage"):
                job.stage = "video_render_failed"

            if hasattr(job, "error"):
                job.error = (
                    f"Failed to fetch rendered video: {exc}"
                )

            update_fields = ["status"]

            if hasattr(job, "stage"):
                update_fields.append("stage")

            if hasattr(job, "error"):
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
                "Failed to apply render result for job %s",
                job_id,
            )

            return JsonResponse(
                {"error": "failed to apply render result"},
                status=500,
            )

    else:
        job.status = (
            "completed"
            if render_status == "success"
            else "failed"
        )

        update_fields = ["status"]

        if hasattr(job, "error"):
            job.error = data.get("error", "")
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
        {"ok": True}
    )