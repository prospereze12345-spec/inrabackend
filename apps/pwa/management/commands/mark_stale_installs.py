from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.pwa.models import PWAInstallation


STALE_INSTALL_DAYS = 14


class Command(BaseCommand):
    help = "Mark PWA installations as inactive when they have not sent a heartbeat recently."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=STALE_INSTALL_DAYS)

        installations = PWAInstallation.objects.filter(
            is_pwa=True,
            is_active=True,
            last_active_at__lt=cutoff,
        )

        count = installations.count()

        if count:
            installations.update(
                is_active=False,
                lost_signal_at=timezone.now(),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Marked {count} stale PWA installation(s) as inactive."
            )
        )