from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .analytics import build_full_analytics
from .geo import get_country_code
from .models import PWAEvent, PWAInstallation
from .serializers import TrackEventSerializer


class TrackPWAEventView(APIView):
    """
    POST /api/pwa/track/
    Public endpoint (anonymous + authenticated visitors both call this).
    Upserts the PWAInstallation row for device_id and appends a PWAEvent.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = TrackEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        now = timezone.now()
        country = get_country_code(request)

        user = request.user if request.user.is_authenticated else None

        installation, _created = PWAInstallation.objects.update_or_create(
            device_id=data["device_id"],
            defaults={
                "os": data["os"],
                "browser": data["browser"],
                "device_type": data["device_type"],
                "country": country,
                "user": user,
                "last_active_at": now,
                "is_active": True,
                "lost_signal_at": None,
            },
        )

        if data["event"] == "install" and not installation.is_pwa:
            installation.is_pwa = True
            installation.installed_at = now
            installation.save(update_fields=["is_pwa", "installed_at"])
        elif data["is_pwa"] and not installation.is_pwa:
            # Fallback: heartbeat arrived from standalone mode without an explicit
            # "install" event (e.g. iOS, where there's no appinstalled signal).
            installation.is_pwa = True
            installation.installed_at = installation.installed_at or now
            installation.save(update_fields=["is_pwa", "installed_at"])

        PWAEvent.objects.create(
            installation=installation,
            event_type=data["event"],
            meta=data.get("meta"),
        )

        return Response({"ok": True}, status=status.HTTP_201_CREATED)


class PWAAnalyticsView(APIView):
    """
    GET /api/pwa/analytics/
    Staff-only dashboard data feed.
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        return Response(build_full_analytics())
