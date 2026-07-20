from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import hashlib


from .models import AIJob
from .tasks import process_ai_job

from rest_framework.parsers import MultiPartParser, FormParser

class CreateAIJobView(APIView):

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):

        print("CONTENT TYPE:", request.content_type)
        print("FILES:", request.FILES)

        image = request.FILES.get("image")

        if not image:
            return Response({"error": "Image required"}, status=400)

        job = AIJob.objects.create(image=image)

        process_ai_job.delay(str(job.id))

        return Response({
            "job_id": str(job.id),
            "status": job.status
        }, status=202)
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


import hashlib
import logging
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AIJob
from .services.renderer import SOCIAL_FORMATS, generate_video, generate_flyer_image
from .services.video_generator import build_promo_props

logger = logging.getLogger(__name__)

FLYER_FORMATS = {
    "png": {"content_type": "image/png", "ext": "png"},
    "pdf": {"content_type": "application/pdf", "ext": "pdf"},
}


class ExportFlyerView(APIView):
    """
    Canva-style single-shot flyer export.
    Renders straight from the live editor state the frontend sends
    (colors, text, uploaded product image, logo) — never trusts stale
    files saved on the AIJob row from when the job was first created.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    EXPORT_DIR = Path(settings.MEDIA_ROOT) / "exports"

    def _get_job(self, job_id):
        return get_object_or_404(AIJob, id=job_id)

    def _validate_format(self, format_id):
        if format_id not in FLYER_FORMATS:
            raise ValueError(
                f"Unknown format '{format_id}'. Available: {list(FLYER_FORMATS)}"
            )

    def post(self, request, job_id, format_id):
        try:
            self._validate_format(format_id)
            job = self._get_job(job_id)

            flyer_data = request.data.get("flyer") or {}
            fmt = FLYER_FORMATS[format_id]

            # Cache on a hash of the live state — identical exports are
            # served instantly, same pattern as the video renderer.
            flyer_hash = hashlib.md5(str(flyer_data).encode()).hexdigest()[:10]
            output_path = self.EXPORT_DIR / f"{job.id}_{format_id}_{flyer_hash}.{fmt['ext']}"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if not output_path.exists():
                props = build_promo_props(job, overrides=flyer_data)
                generate_flyer_image(
                    props=props,
                    output_path=str(output_path),
                    format=format_id,
                )

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("Flyer render produced no output.")

            return FileResponse(
                output_path.open("rb"),
                as_attachment=True,
                filename=f"flyer-{job.id}.{fmt['ext']}",
                content_type=fmt["content_type"],
            )

        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Flyer export failed for job %s", job_id)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RenderFormatVideoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    VIDEO_DIR = Path(settings.MEDIA_ROOT) / "videos"

    def _get_job(self, job_id):
        return get_object_or_404(AIJob, id=job_id)

    def _validate_format(self, format_id):
        if format_id not in SOCIAL_FORMATS:
            raise ValueError(
                f"Unknown format '{format_id}'. Available formats: {list(SOCIAL_FORMATS.keys())}"
            )

    def _render_video(self, job, format_id, output_path, overrides=None):
        props = build_promo_props(job, overrides=overrides)
        generate_video(
            props=props,
            output_path=str(output_path),
            format_name=format_id,
            verbose=False,
        )

    def get(self, request, job_id, format_id):
        try:
            self._validate_format(format_id)
            job = self._get_job(job_id)

            video_path = self.VIDEO_DIR / f"{job.id}_{format_id}.mp4"
            if not video_path.exists():
                self._render_video(job, format_id, video_path)

            return FileResponse(
                video_path.open("rb"),
                as_attachment=True,
                filename=f"promo-{format_id}.mp4",
                content_type="video/mp4",
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Video render failed")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, job_id, format_id):
        try:
            self._validate_format(format_id)
            job = self._get_job(job_id)

            flyer_data = request.data.get("flyer") or {}
            flyer_hash = hashlib.md5(str(flyer_data).encode()).hexdigest()[:10]
            output = self.VIDEO_DIR / f"{job.id}_{format_id}_{flyer_hash}.mp4"

            if not output.exists():
                self._render_video(job, format_id, output, overrides=flyer_data)

            if not output.exists() or output.stat().st_size == 0:
                raise RuntimeError("Video render produced no output.")

            return FileResponse(
                output.open("rb"),
                as_attachment=True,
                filename=f"promo-{format_id}.mp4",
                content_type="video/mp4",
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Live render failed")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




















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