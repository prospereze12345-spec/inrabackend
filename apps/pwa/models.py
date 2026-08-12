from django.conf import settings
from django.db import models
from django.utils import timezone


class PWAInstallation(models.Model):
    """
    One row per anonymous device_id we've ever seen. This is the source of
    truth for "Installations" / "Active installs" / device+OS+country
    breakdowns. It's updated (not re-created) on every event for that device.
    """

    DEVICE_TYPES = [
        ("mobile", "Mobile"),
        ("tablet", "Tablet"),
        ("desktop", "Desktop"),
    ]

    device_id = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pwa_installations",
    )

    os = models.CharField(max_length=32, db_index=True)
    browser = models.CharField(max_length=32)
    device_type = models.CharField(max_length=16, choices=DEVICE_TYPES, db_index=True)
    country = models.CharField(max_length=2, null=True, blank=True, db_index=True)

    is_pwa = models.BooleanField(default=False, help_text="True once we've seen this device running standalone")
    installed_at = models.DateTimeField(null=True, blank=True, help_text="First confirmed 'install' event")

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(db_index=True)

    is_active = models.BooleanField(default=True, db_index=True)
    lost_signal_at = models.DateTimeField(
        null=True, blank=True, help_text="Set when no heartbeat received for STALE_INSTALL_DAYS"
    )

    class Meta:
        indexes = [
            models.Index(fields=["is_pwa", "is_active"]),
            models.Index(fields=["os", "device_type"]),
        ]

    def __str__(self):
        return f"{self.device_id[:8]} ({self.os}/{self.browser})"

    def mark_lost_signal(self):
        self.is_active = False
        self.lost_signal_at = timezone.now()
        self.save(update_fields=["is_active", "lost_signal_at"])


class PWAEvent(models.Model):
    """Append-only event log — every prompt/install/session ping lands here too."""

    EVENT_TYPES = [
        ("prompt_shown", "Install prompt shown"),
        ("prompt_accepted", "Install prompt accepted"),
        ("prompt_dismissed", "Install prompt dismissed"),
        ("install", "Installed"),
        ("session", "Session heartbeat"),
        ("ios_instructions_shown", "iOS instructions shown"),
        ("lost_signal", "Lost install signal (system-generated)"),
    ]

    installation = models.ForeignKey(PWAInstallation, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=32, choices=EVENT_TYPES, db_index=True)
    meta = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["event_type", "created_at"])]
        ordering = ["-created_at"]
