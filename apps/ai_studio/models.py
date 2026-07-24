import uuid
from django.conf import settings
from django.db import models


class AIJob(models.Model):

    STATUS = (
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )

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
    flyer_props = models.JSONField(null=True, blank=True)  # ✅ NEW
    video = models.FileField(upload_to="videos/", null=True, blank=True)

    captions = models.JSONField(default=dict)

    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    error = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    image_nobg = models.ImageField(
        upload_to="nobg/",
        null=True,
        blank=True,
    )