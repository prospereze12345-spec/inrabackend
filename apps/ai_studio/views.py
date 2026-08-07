from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import hashlib


from .models import AIJob
from .services.qstash_client import enqueue_ai_job

from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from rest_framework.permissions import IsAuthenticated

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
        try:
            job = AIJob.objects.get(id=job_id)
        except AIJob.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        # Normalise your internal statuses to what the frontend polls for
        status_map = {
            "pending":    "pending",
            "processing": "processing",
            "completed":  "done",
            "failed":     "error",
        }
        return Response({
            "job_id": str(job.id),
            "status": status_map.get(job.status, "pending"),
        })
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


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
            job = AIJob.objects.get(id=job_id)
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

        # ─────────────────────────────────────────────
        # Captions
        # ─────────────────────────────────────────────
        raw_captions = (job.captions or {}).get("captions", {})

        captions = [
            {
                "platform": label,
                "text": raw_captions[key],
            }
            for key, label in self.PLATFORM_MAP.items()
            if raw_captions.get(key)
        ]

        # ─────────────────────────────────────────────
        # Flyer props
        # ─────────────────────────────────────────────
        flyer = {
            **(job.flyer_props or {}),
            "productImage": (
                self._absolute_url(request, job.image_nobg)
                or ""
            ),
        }

        # ─────────────────────────────────────────────
        # Video URL
        # Supports both:
        # 1. Django FileField
        # 2. Remotion URL string
        # ─────────────────────────────────────────────
        video_url = None

        if job.video:
            try:
                video_url = request.build_absolute_uri(
                    job.video.url
                )
            except Exception:
                video_url = str(job.video)

        # ─────────────────────────────────────────────
        # Response
        # ─────────────────────────────────────────────
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
            .filter(user=request.user, status="completed")
            .order_by("-created_at")[:20]
        )

        results = [
            {
                "job_id": str(job.id),
                "headline": (job.flyer_props or {}).get("headline"),
                "png_url": self._absolute_url(request, job.image_nobg),
                "template_category": (job.flyer_props or {}).get("templateCategory"),
                "created_at": job.created_at.isoformat(),
            }
            for job in jobs
        ]

        return Response(results, status=status.HTTP_200_OK)



# views.py
import uuid
import os
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage

@csrf_exempt  # only for now in dev — we'll tighten this later
def upload_asset(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file provided"}, status=400)

    # give it a unique name so uploads never overwrite each other
    ext = os.path.splitext(file.name)[1]
    filename = f"uploads/{uuid.uuid4().hex}{ext}"

    saved_path = default_storage.save(filename, file)
    file_url = request.build_absolute_uri(settings.MEDIA_URL + saved_path)

    return JsonResponse({"url": file_url})








# campaign/views.py  (add this)
import hmac
import json
import logging

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import AIJob

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def video_render_complete(request):
    provided = request.headers.get("X-Callback-Secret", "")
    if not hmac.compare_digest(provided, settings.RENDER_CALLBACK_SECRET):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
        job_id = data["job_id"]
        status = data["status"]  # "success" | "failed"
    except (KeyError, ValueError):
        return JsonResponse({"error": "bad request"}, status=400)

    try:
        job = AIJob.objects.get(id=job_id)
    except AIJob.DoesNotExist:
        logger.warning("video_render_complete: no AIJob with id=%s", job_id)
        return JsonResponse({"error": "job not found"}, status=404)

    if status != "success":
        job.status = "failed"
        job.stage = "video_render_failed"
        job.error = data.get("error", "GitHub Actions render failed")
        job.save(update_fields=["status", "stage", "error"])
        return JsonResponse({"ok": True})

    video_url = data.get("video_url")
    if not video_url:
        job.status = "failed"
        job.stage = "video_render_failed"
        job.error = "Render reported success but no video_url was provided"
        job.save(update_fields=["status", "stage", "error"])
        return JsonResponse({"error": "missing video_url"}, status=400)

    try:
        resp = requests.get(video_url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch rendered video for job %s: %s", job_id, e)
        job.status = "failed"
        job.stage = "video_render_failed"
        job.error = f"Failed to fetch rendered video: {e}"
        job.save(update_fields=["status", "stage", "error"])
        return JsonResponse({"error": "fetch failed"}, status=502)

    job.video.save(f"{job.id}.mp4", ContentFile(resp.content), save=False)
    job.status = "completed"
    job.stage = "completed"
    job.error = None
    job.save(update_fields=["video", "status", "stage", "error"])

    logger.info("Job %s → video ready", job_id)
    return JsonResponse({"ok": True})

import json
import mimetypes
import tempfile
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services.renderer import SOCIAL_FORMATS, generate_video, normalize_promo_props


@csrf_exempt
@require_POST
def render_video_view(request):
    """
    POST /api/campaign/render-video/

    Body (JSON):
        {
          "format": "ig" | "square" | "story" | "yt" | "tiktok" | "banner",
          "props": { ...the exact `promoProps` object the editor's
                     <Player> preview is already using... }
        }

    Renders the PromoVideo composition server-side, via the same
    remotion/render.mjs + PromoVideo.tsx pipeline used everywhere else,
    using exactly the props the live preview shows — so the downloaded
    video matches the on-canvas preview pixel-for-pixel, animation
    timing included. Streams the resulting MP4 back as a file download.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

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

    props = normalize_promo_props(payload.get("props"))

    output_dir = Path(settings.MEDIA_ROOT) / "renders"
    output_dir.mkdir(parents=True, exist_ok=True)
    unique = next(tempfile._get_candidate_names())
    output_path = output_dir / f"promo-{format_name}-{unique}.mp4"

    try:
        rendered_path = generate_video(
            props=props,
            output_path=str(output_path),
            format_name=format_name,
            verbose=False,
        )
    except Exception as exc:  # surfaces render.mjs / subprocess failures
        return JsonResponse({"error": f"Render failed: {exc}"}, status=500)

    response = FileResponse(
        open(rendered_path, "rb"),
        content_type=mimetypes.guess_type(str(rendered_path))[0] or "video/mp4",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="promo-{format_name}.mp4"'
    )
    return response