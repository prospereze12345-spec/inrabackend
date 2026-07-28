from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.accounts.models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display   = ("email", "full_name", "country", "is_verified", "is_active", "created_at")
    list_filter    = ("is_verified", "is_active", "country")
    search_fields  = ("email", "full_name")
    ordering       = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (None,           {"fields": ("id", "email", "password")}),
        ("Personal Info", {"fields": ("full_name", "country")}),
        ("Status",       {"fields": ("is_verified", "is_active", "is_staff", "is_superuser")}),
        ("Timestamps",   {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "country", "password1", "password2")}),
    )
