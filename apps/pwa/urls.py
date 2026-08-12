from django.urls import path

from .views import PWAAnalyticsView, TrackPWAEventView

urlpatterns = [
    path("track/", TrackPWAEventView.as_view(), name="pwa-track"),
    path("analytics/", PWAAnalyticsView.as_view(), name="pwa-analytics"),
]
