from django.urls import path

from .views import (
    CreateAIJobView,
    JobStatusView,
    JobResultView,
    RecentCampaignsView,  
    upload_asset,
)

urlpatterns = [
    path("generate/", CreateAIJobView.as_view(), name="generate"),
    path("recent/", RecentCampaignsView.as_view(), name="recent-campaigns"),   
    
    path("status/<uuid:job_id>/", JobStatusView.as_view(), name="job-status"),
    path("result/<uuid:job_id>/", JobResultView.as_view(), name="job-result"),
    path("uploads/", upload_asset, name="upload_asset"),
]



