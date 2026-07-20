from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/campaign/", include("apps.ai_studio.urls")),
    path("api/", include("apps.pricing.urls", namespace="pricing")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # In production: configure nginx to serve MEDIA_ROOT at MEDIA_URL
    # OR use django-storages with S3
    pass