from django.contrib import admin

from .models import PWAEvent, PWAInstallation


@admin.register(PWAInstallation)
class PWAInstallationAdmin(admin.ModelAdmin):
    list_display = ("device_id", "os", "browser", "device_type", "country", "is_pwa", "is_active", "last_active_at")
    list_filter = ("os", "browser", "device_type", "country", "is_pwa", "is_active")
    search_fields = ("device_id", "user__email", "user__username")
    readonly_fields = ("first_seen_at",)


@admin.register(PWAEvent)
class PWAEventAdmin(admin.ModelAdmin):
    list_display = ("installation", "event_type", "created_at")
    list_filter = ("event_type",)
    readonly_fields = ("created_at",)
