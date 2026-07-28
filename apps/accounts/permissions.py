from rest_framework.permissions import BasePermission, IsAuthenticated


class IsVerifiedUser(IsAuthenticated):
    message = "Email verification required."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and bool(getattr(request.user, "is_verified", False))


class IsActiveUser(IsAuthenticated):
    message = "Your account has been deactivated."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and bool(getattr(request.user, "is_active", False))
