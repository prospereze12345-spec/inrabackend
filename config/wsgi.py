import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Force the rembg model to load now, at worker boot, instead of on
# the first incoming request. If this raises or hangs, you want it
# to fail loudly at startup, not inside a webhook handler.
from apps.ai_studio.services.background_removal import _session  # noqa: F401, E402