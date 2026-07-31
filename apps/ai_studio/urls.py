from django.urls import path
from . import webhooks


from .views import (
    CreateAIJobView,
    JobStatusView,
    JobResultView,
    RecentCampaignsView,  
    upload_asset,
    render_video_view,
)

urlpatterns = [
    path("render-video/", render_video_view, name="render-video"),
    path("generate/", CreateAIJobView.as_view(), name="generate"),
    path("recent/", RecentCampaignsView.as_view(), name="recent-campaigns"),   
    path("qstash/webhook/", webhooks.qstash_webhook, name="qstash-webhook"),
    path("status/<uuid:job_id>/", JobStatusView.as_view(), name="job-status"),
    path("result/<uuid:job_id>/", JobResultView.as_view(), name="job-result"),
    path("uploads/", upload_asset, name="upload_asset"),
]



