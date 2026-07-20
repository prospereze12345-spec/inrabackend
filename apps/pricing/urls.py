from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PricingViewSet

app_name = "pricing"

router = DefaultRouter()
router.register(r"pricing", PricingViewSet, basename="pricing")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "pricing/webhook/",
        PricingViewSet.as_view({"post": "webhook"}),
        name="webhook",
    ),
]