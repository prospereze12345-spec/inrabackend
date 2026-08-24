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
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AIJob, PreviewRenderJob
from .promo import apply_render_result, dispatch_preview_render
from .services.qstash_client import enqueue_ai_job
from .services.renderer import SOCIAL_FORMATS, normalize_promo_props

logger = logging.getLogger(__name__)


class CreateAIJobView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        image = request.FILES.get("image")
        if not image:
            return Response({"error": "Image required"}, status=400)

        job = AIJob.objects.create(image=image, user=request.user)
        enqueue_ai_job(str(job.id))

        return Response({"job_id": str(job.id), "status": job.status}, status=202)

class JobStatusView(APIView):
    def get(self, request, job_id):
        job, job_kind = None, None
        try:
            job = AIJob.objects.get(id=job_id)
            job_kind = "aijob"
        except AIJob.DoesNotExist:
            try:
                job = PreviewRenderJob.objects.get(id=job_id)
                job_kind = "preview"
            except PreviewRenderJob.DoesNotExist:
                logger.warning("JobStatusView: no job found for id=%s", job_id)
                return Response({"error": "job not found"}, status=status.HTTP_404_NOT_FOUND)

        if job_kind == "aijob":
            status_map = {
                "pending":    "pending",
                "processing": "processing",
                "completed":  "done",
                "failed":     "error",
            }
        else:
            # PreviewRenderJob only ever moves through processing → completed/failed
            # (see render_video_view / dispatch_preview_render)
            status_map = {
                "processing": "processing",
                "completed":  "done",
                "failed":     "error",
            }

        return Response({
            "job_id": str(job.id),
            "status": status_map.get(job.status, "pending"),
        })
@csrf_exempt
def upload_asset(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file provided"}, status=400)

    ext = os.path.splitext(file.name)[1]
    filename = f"uploads/{uuid.uuid4().hex}{ext}"

    saved_path = default_storage.save(filename, file)

    # Ask the storage backend for the correct URL — works whether it's
    # local disk, Cloudinary, S3, or anything else. Never hand-build this.
    raw_url = default_storage.url(saved_path)

    # default_storage.url() already returns an absolute URL for Cloudinary;
    # for local storage it returns a relative path, so only build_absolute_uri
    # it if it isn't already absolute.
    file_url = raw_url if raw_url.startswith("http") else request.build_absolute_uri(raw_url)

    return JsonResponse({"url": file_url})

    
@csrf_exempt
@require_POST
def render_video_view(request):
    """
    One-off editor-preview export. Dispatches to GitHub Actions and returns
    immediately with a job_id to poll — does NOT render synchronously.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    format_name = payload.get("format", "ig")
    if format_name not in SOCIAL_FORMATS:
        return JsonResponse(
            {"error": f"Unknown format '{format_name}'. Available: {list(SOCIAL_FORMATS.keys())}"},
            status=400,
        )

    props = normalize_promo_props(payload.get("props"))

    job = PreviewRenderJob.objects.create(status="processing", stage="rendering_video")

    try:
        dispatch_preview_render(job, props=props, format_name=format_name)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.save(update_fields=["status", "error"])
        return JsonResponse({"error": f"Render dispatch failed: {exc}"}, status=500)

    return JsonResponse({"job_id": str(job.id), "status": "processing"}, status=202)

@csrf_exempt
@require_POST
def video_render_complete(request):
    provided = request.headers.get("X-Callback-Secret", "")
    if not hmac.compare_digest(provided, settings.RENDER_CALLBACK_SECRET):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
        job_id = data["job_id"]
        render_status = data["status"]  # renamed from `status` — was shadowing the DRF import
    except (KeyError, ValueError):
        return JsonResponse({"error": "bad request"}, status=400)

    job, job_kind = None, None
    try:
        job = AIJob.objects.get(id=job_id)
        job_kind = "aijob"
    except AIJob.DoesNotExist:
        try:
            job = PreviewRenderJob.objects.get(id=job_id)
            job_kind = "preview"
        except PreviewRenderJob.DoesNotExist:
            logger.warning("video_render_complete: no job found for id=%s", job_id)
            return JsonResponse({"error": "job not found"}, status=404)

    if job_kind == "aijob":
        try:
            apply_render_result(
                job,
                success=(render_status == "success"),
                video_url=data.get("video_url", ""),
                error=data.get("error", ""),
            )
        except requests.RequestException as e:
            logger.error("Failed to fetch rendered video for job %s: %s", job_id, e)
            job.status = "failed"
            job.stage = "video_render_failed"
            job.error = f"Failed to fetch rendered video: {e}"
            job.save(update_fields=["status", "stage", "error"])
            return JsonResponse({"error": "fetch failed"}, status=502)
    else:
        # PreviewRenderJob is a lighter record than AIJob — no external
        # fetch/apply step, just record the outcome GitHub already gave us.
        job.status = "completed" if render_status == "success" else "failed"
        job.error = data.get("error", "")
        update_fields = ["status", "error"]
        if hasattr(job, "video_url"):
            job.video_url = data.get("video_url", "")
            update_fields.append("video_url")
        job.save(update_fields=update_fields)

    return JsonResponse({"ok": True})