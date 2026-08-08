import uuid

from django.conf import settings
from django.db import models

from cloudinary_storage.storage import VideoMediaCloudinaryStorage


JOB_STATUS_CHOICES = (
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("failed", "Failed"),
)


class AIJob(models.Model):

    STATUS = JOB_STATUS_CHOICES  # kept for backward compat with any code using AIJob.STATUS

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_jobs",
        null=True,   # existing rows have no owner — must stay nullable
        blank=True,
    )

    stage = models.CharField(max_length=64, default="pending", blank=True)
    image = models.ImageField(upload_to="uploads/")
    flyer = models.ImageField(upload_to="flyers/", null=True, blank=True)
    flyer_props = models.JSONField(null=True, blank=True)
    video = models.FileField(
        upload_to="videos/",
        null=True,
        blank=True,
        storage=VideoMediaCloudinaryStorage(),
    )

    captions = models.JSONField(default=dict)

    status = models.CharField(max_length=20, choices=JOB_STATUS_CHOICES, default="pending")
    error = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    image_nobg = models.ImageField(
        upload_to="nobg/",
        null=True,
        blank=True,
    )


class PreviewRenderJob(models.Model):
    """
    Tracks one-off editor-preview video exports (render_video_view), which
    have no associated uploaded product image and therefore can't reuse
    AIJob — AIJob.image is required.
    """

    STATUS = JOB_STATUS_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preview_renders",
        null=True,
        blank=True,
    )

    stage = models.CharField(max_length=64, default="pending", blank=True)
    status = models.CharField(max_length=20, choices=JOB_STATUS_CHOICES, default="pending")
    video = models.FileField(
        upload_to="videos/",
        null=True,
        blank=True,
        storage=VideoMediaCloudinaryStorage(),
    )
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)