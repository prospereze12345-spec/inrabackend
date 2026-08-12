from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import PWAEvent, PWAInstallation

DAU_WINDOW_HOURS = 24
DAILY_TREND_DAYS = 30


def build_summary():
    now = timezone.now()
    dau_cutoff = now - timedelta(hours=DAU_WINDOW_HOURS)

    total_installs = PWAInstallation.objects.filter(is_pwa=True).count()
    active_installs = PWAInstallation.objects.filter(is_pwa=True, is_active=True).count()
    lost_signal_installs = PWAInstallation.objects.filter(is_pwa=True, is_active=False).count()

    dau_qs = PWAInstallation.objects.filter(last_active_at__gte=dau_cutoff)
    dau = dau_qs.count()
    pwa_users = dau_qs.filter(is_pwa=True).count()
    browser_users = dau_qs.filter(is_pwa=False).count()

    return {
        "total_installs": total_installs,
        "active_installs": active_installs,
        "lost_signal_installs": lost_signal_installs,
        "dau": dau,
        "pwa_users": pwa_users,
        "browser_users": browser_users,
    }


def build_daily_trend():
    since = timezone.now() - timedelta(days=DAILY_TREND_DAYS)

    dau_by_day = (
        PWAEvent.objects.filter(event_type="session", created_at__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(dau=Count("installation_id", distinct=True))
        .order_by("day")
    )
    installs_by_day = (
        PWAEvent.objects.filter(event_type="install", created_at__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(installs=Count("id"))
        .order_by("day")
    )

    dau_map = {row["day"]: row["dau"] for row in dau_by_day}
    installs_map = {row["day"]: row["installs"] for row in installs_by_day}
    all_days = sorted(set(dau_map) | set(installs_map))

    return [
        {"date": d.isoformat(), "dau": dau_map.get(d, 0), "installs": installs_map.get(d, 0)}
        for d in all_days
    ]


def build_breakdowns():
    by_device_type = list(
        PWAInstallation.objects.values("device_type").annotate(count=Count("id")).order_by("-count")
    )
    by_os = list(PWAInstallation.objects.values("os").annotate(count=Count("id")).order_by("-count"))
    by_country = list(
        PWAInstallation.objects.exclude(country__isnull=True)
        .values("country")
        .annotate(count=Count("id"))
        .order_by("-count")[:20]
    )
    return by_device_type, by_os, by_country


def build_recent(limit=50):
    qs = PWAInstallation.objects.order_by("-last_active_at")[:limit]
    return [
        {
            "device_id": row.device_id,
            "os": row.os,
            "browser": row.browser,
            "device_type": row.device_type,
            "country": row.country,
            "is_pwa": row.is_pwa,
            "last_active_at": row.last_active_at.isoformat(),
        }
        for row in qs
    ]


def build_full_analytics():
    by_device_type, by_os, by_country = build_breakdowns()
    return {
        "summary": build_summary(),
        "daily": build_daily_trend(),
        "by_device_type": by_device_type,
        "by_os": by_os,
        "by_country": by_country,
        "recent": build_recent(),
    }
