# apps/accounts/utils.py
import secrets
import logging
from typing import Optional
from django.conf import settings
import redis

logger = logging.getLogger(__name__)

MAGIC_LINK_TTL    = 15 * 60
RATE_LIMIT_WINDOW = 60 * 60
AUDIT_LOG_TTL     = 7 * 24 * 60 * 60

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        url = getattr(settings, "UPSTASH_REDIS_URL", None)
        if not url:
            raise RuntimeError(
                "UPSTASH_REDIS_URL is not configured. "
                "Set it in Render's environment variables."
            )
        _redis_client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client