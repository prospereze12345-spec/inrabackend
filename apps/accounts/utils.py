import secrets
import logging
from typing import Optional
from django.conf import settings
import redis

logger = logging.getLogger(__name__)

MAGIC_LINK_TTL    = 15 * 60
RATE_LIMIT_WINDOW = 60 * 60
AUDIT_LOG_TTL     = 7 * 24 * 60 * 60


def get_redis() -> redis.Redis:
    return redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def generate_magic_token() -> str:
    return secrets.token_urlsafe(48)


def store_magic_token(token: str, email: str) -> bool:
    try:
        get_redis().setex(f"magic:{token}", MAGIC_LINK_TTL, email)
        return True
    except redis.RedisError as e:
        logger.error("Redis store error: %s", e)
        return False


def get_magic_token_email(token: str) -> Optional[str]:
    try:
        return get_redis().get(f"magic:{token}")
    except redis.RedisError as e:
        logger.error("Redis get error: %s", e)
        return None


def delete_magic_token(token: str) -> None:
    try:
        get_redis().delete(f"magic:{token}")
    except redis.RedisError as e:
        logger.error("Redis delete error: %s", e)


def _check_rate_limit(key: str, max_attempts: int, window: int = RATE_LIMIT_WINDOW) -> tuple[bool, int]:
    try:
        r = get_redis()
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if ttl == -1:
            r.expire(key, window)
        return count <= max_attempts, int(count)
    except redis.RedisError as e:
        logger.error("Rate limit Redis error: %s", e)
        return True, 0  # fail open


def check_signup_rate_limit(email: str, ip: str) -> tuple[bool, str]:
    ok, _ = _check_rate_limit(f"rl:signup:email:{email.lower()}", 5)
    if not ok:
        return False, "Too many signup attempts for this email. Try again in an hour."
    ok, _ = _check_rate_limit(f"rl:signup:ip:{ip}", 20)
    if not ok:
        return False, "Too many signup attempts from this IP. Try again in an hour."
    return True, ""


def check_login_rate_limit(email: str, ip: str) -> tuple[bool, str]:
    ok, _ = _check_rate_limit(f"rl:login:email:{email.lower()}", 5)
    if not ok:
        return False, "Too many login attempts for this email. Try again in an hour."
    ok, _ = _check_rate_limit(f"rl:login:ip:{ip}", 20)
    if not ok:
        return False, "Too many login attempts from this IP. Try again in an hour."
    return True, ""


def check_verify_rate_limit(ip: str) -> tuple[bool, str]:
    ok, _ = _check_rate_limit(f"rl:verify:ip:{ip}", 20)
    if not ok:
        return False, "Too many verification attempts. Try again in an hour."
    return True, ""


def audit_log(action: str, email: str, ip: str, extra: str = "") -> None:
    import time
    try:
        r = get_redis()
        key = f"audit:{action}:{email.lower()}"
        r.lpush(key, f"{int(time.time())}|{ip}|{extra}")
        r.ltrim(key, 0, 99)
        r.expire(key, AUDIT_LOG_TTL)
    except redis.RedisError as e:
        logger.error("Audit log Redis error: %s", e)


def get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")
