import logging

from django.core.cache import cache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def get_cached(key):
    """Fetch from cache. Returns None on a cache miss OR if Redis itself
    is unavailable/slow — callers should already treat None as 'go compute it'."""
    try:
        return cache.get(key)
    except RedisError as e:
        logger.warning("Redis GET failed for key=%s, treating as cache miss: %s", key, e)
        return None


def set_cached(key, value, timeout=86400):
    """Write to cache. Failures are logged and swallowed — a cache write
    should never be able to fail a job."""
    try:
        cache.set(key, value, timeout)
    except RedisError as e:
        logger.warning("Redis SET failed for key=%s, skipping cache write: %s", key, e)