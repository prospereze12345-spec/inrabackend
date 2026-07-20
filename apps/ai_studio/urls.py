from django.urls import path

from .views import (
    CreateAIJobView,
    JobStatusView,
    JobResultView,upload_asset,
    ExportFlyerView, RenderFormatVideoView
)

urlpatterns = [
    path("generate/", CreateAIJobView.as_view(), name="generate"),
    path(
        "export/<uuid:job_id>/flyer/<str:format_id>/",
        ExportFlyerView.as_view(),
        name="export-flyer",
    ),
    path(
        "export/<uuid:job_id>/video/<str:format_id>/",
        RenderFormatVideoView.as_view(),
        name="export-video-format",
    ),
    path("status/<uuid:job_id>/", JobStatusView.as_view(), name="job-status"),
    path("result/<uuid:job_id>/", JobResultView.as_view(), name="job-result"),
    path("uploads/", upload_asset, name="upload_asset"),

]



