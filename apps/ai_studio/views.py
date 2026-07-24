from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import hashlib


from .models import AIJob
from .tasks import process_ai_job

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
        process_ai_job.delay(str(job.id))

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