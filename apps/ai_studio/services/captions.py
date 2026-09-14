import hashlib
import json
import logging
from typing import Any

import requests
from django.conf import settings

from ..grok_client import GROQ_URL, HEADERS
from ..prompts.caption_prompt import build_caption_prompt
from ..utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Groq configuration
# ---------------------------------------------------------------------------

GROQ_MODEL = getattr(
    settings,
    "GROQ_CAPTION_MODEL",
    "openai/gpt-oss-120b",
)

GROQ_TIMEOUT = getattr(
    settings,
    "GROQ_REQUEST_TIMEOUT",
    120,
)

# Keep the completion bounded. This is a single structured response containing
# flyer copy + captions + hashtags + hooks.
GROQ_MAX_COMPLETION_TOKENS = getattr(
    settings,
    "GROQ_MAX_COMPLETION_TOKENS",
    1200,
)

GROQ_REASONING_EFFORT = getattr(
    settings,
    "GROQ_REASONING_EFFORT",
    "low",
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONTACT_PLACEHOLDERS = {
    "phone": "+234 800 000 0000",
    "email": "hello@yourbrand.com",
    "website": "www.yourbrand.com",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class CaptionGenerationError(Exception):
    """
    Controlled exception for the caption-generation pipeline.

    retryable=True means the caller may safely retry the job later.
    Configuration errors, invalid model parameters, malformed AI output,
    authentication failures, etc. are deliberately non-retryable.
    """

    def __init__(
        self,
        stage: str,
        message: str,
        raw: Any = None,
        retryable: bool = False,
    ):
        self.stage = stage
        self.message = message
        self.raw = raw
        self.retryable = retryable

        super().__init__(f"[{stage}] {message}")

    def __reduce__(self):
        return (
            self.__class__,
            (
                self.stage,
                self.message,
                self.raw,
                self.retryable,
            ),
        )

    @property
    def is_retryable(self) -> bool:
        return self.retryable


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _build_session() -> requests.Session:
    """
    Build a plain HTTP session.

    We intentionally do NOT retry inside requests.

    QStash/job-level retry logic already exists upstream. Retrying here could
    generate duplicate AI requests and therefore waste tokens.
    """
    return requests.Session()


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are INRASTUDIO's marketing copy engine for African social commerce.

Create concise, high-converting product marketing copy for small businesses.
Optimize for WhatsApp, Instagram and TikTok sales.

Rules:
- Return ONLY valid JSON.
- No markdown or explanation.
- Never invent product facts, prices, contacts or claims.
- Every caption must be ready to publish.
- Keep copy concise and commercially useful.
"""


# ---------------------------------------------------------------------------
# Groq API
# ---------------------------------------------------------------------------

def _groq_error_message(response: requests.Response) -> str:
    """
    Extract a safe, human-readable provider error.

    We log enough information to diagnose provider failures without dumping
    large responses or request contents into production logs.
    """
    try:
        data = response.json()

        error = data.get("error")

        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)[:500]

        if isinstance(error, str):
            return error[:500]

        message = data.get("message")
        if message:
            return str(message)[:500]

    except (ValueError, TypeError):
        pass

    text = (response.text or "").strip()

    if text:
        return text[:500]

    return "Groq returned an empty error response."


def _call_groq(prompt: str) -> dict:
    """
    Make exactly one Groq request.

    Retry policy is intentionally delegated to the outer job system so an
    LLM request cannot silently execute multiple times and consume tokens.
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise CaptionGenerationError(
            "input_error",
            "Caption prompt is empty.",
        )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT.strip(),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],

        # GPT-OSS supports reasoning effort. Low is sufficient for structured
        # marketing copy and avoids unnecessary reasoning-token consumption.
        "reasoning_effort": GROQ_REASONING_EFFORT,

        # Do not return reasoning content to the application.
        "include_reasoning": False,

        # Current Groq API uses max_completion_tokens.
        "max_completion_tokens": GROQ_MAX_COMPLETION_TOKENS,

        # JSON is required by the downstream parser.
        "response_format": {
            "type": "json_object",
        },

        # Low temperature keeps commercial copy reasonably consistent.
        "temperature": 0.2,
    }

    session = _build_session()

    try:
        response = session.post(
            GROQ_URL,
            headers=HEADERS,
            json=payload,
            timeout=GROQ_TIMEOUT,
        )

    except requests.Timeout as exc:
        logger.warning(
            "Groq request timed out after %ss.",
            GROQ_TIMEOUT,
        )

        raise CaptionGenerationError(
            "request_error",
            "Caption generation timed out. Please try again.",
            retryable=True,
        ) from exc

    except requests.ConnectionError as exc:
        logger.warning("Groq connection failed.")

        raise CaptionGenerationError(
            "request_error",
            "Could not connect to the caption service.",
            retryable=True,
        ) from exc

    except requests.RequestException as exc:
        logger.warning(
            "Groq HTTP request failed: %s",
            type(exc).__name__,
        )

        raise CaptionGenerationError(
            "request_error",
            "Caption service request failed.",
            retryable=True,
        ) from exc

    finally:
        session.close()

    # -----------------------------------------------------------------------
    # Success
    # -----------------------------------------------------------------------

    if response.status_code == 200:
        try:
            result = response.json()
        except ValueError as exc:
            logger.error("Groq returned non-JSON HTTP 200 response.")

            raise CaptionGenerationError(
                "invalid_provider_response",
                "Caption service returned an invalid response.",
            ) from exc

        if not isinstance(result, dict):
            raise CaptionGenerationError(
                "malformed_response",
                "Caption service returned an unexpected response.",
            )

        return result

    # -----------------------------------------------------------------------
    # Client/configuration errors
    #
    # These should NOT be retried.
    # -----------------------------------------------------------------------

    if response.status_code in {400, 401, 403, 404, 422}:
        provider_message = _groq_error_message(response)

        logger.error(
            "Groq rejected caption request: HTTP %s: %s",
            response.status_code,
            provider_message,
        )

        if response.status_code == 401:
            message = "Caption service authentication failed."

        elif response.status_code == 403:
            message = "Caption service access was denied."

        elif response.status_code == 404:
            message = "Configured caption model or endpoint is unavailable."

        elif response.status_code == 422:
            message = "Caption request contains invalid parameters."

        else:
            message = "Caption request was rejected by the AI service."

        raise CaptionGenerationError(
            "api_error",
            message,
            raw={
                "status_code": response.status_code,
                "provider_message": provider_message,
            },
            retryable=False,
        )

    # -----------------------------------------------------------------------
    # Rate limiting
    #
    # Let the outer job system retry this later.
    # -----------------------------------------------------------------------

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")

        logger.warning(
            "Groq rate limit reached. retry_after=%s",
            retry_after or "unknown",
        )

        raise CaptionGenerationError(
            "rate_limited",
            "Caption service is temporarily busy. Please retry shortly.",
            retryable=True,
        )

    # -----------------------------------------------------------------------
    # Provider/server failures
    # -----------------------------------------------------------------------

    if response.status_code in {500, 502, 503, 504}:
        logger.warning(
            "Groq temporary provider failure: HTTP %s",
            response.status_code,
        )

        raise CaptionGenerationError(
            "provider_error",
            "Caption service is temporarily unavailable.",
            retryable=True,
        )

    # -----------------------------------------------------------------------
    # Unknown HTTP status
    # -----------------------------------------------------------------------

    logger.error(
        "Unexpected Groq HTTP status: %s",
        response.status_code,
    )

    raise CaptionGenerationError(
        "api_error",
        "Caption service returned an unexpected error.",
        raw={"status_code": response.status_code},
        retryable=False,
    )


# ---------------------------------------------------------------------------
# Response extraction
# ---------------------------------------------------------------------------

def _extract_content(result: dict) -> str:
    try:
        content = result["choices"][0]["message"]["content"]

    except (KeyError, IndexError, TypeError) as exc:
        logger.error(
            "Groq response missing expected message content."
        )

        raise CaptionGenerationError(
            "malformed_response",
            "Caption service returned an unexpected response.",
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise CaptionGenerationError(
            "empty_content",
            "Caption service returned no usable content.",
        )

    return content.strip()


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_captions(content: str) -> dict:
    """
    Parse Groq's JSON response.

    JSON mode should normally make the first json.loads() succeed.
    The fallback exists only as a defensive compatibility layer.
    """

    content = content.strip()

    # Defensive cleanup for models/providers that still return fences.
    if content.startswith("```json"):
        content = content[7:].strip()

    elif content.startswith("```"):
        content = content[3:].strip()

    if content.endswith("```"):
        content = content[:-3].strip()

    try:
        parsed = json.loads(content)

    except json.JSONDecodeError:
        parsed = None

    if parsed is None:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            parsed = json.loads(content[start:end])

        except (ValueError, json.JSONDecodeError) as exc:
            logger.error(
                "Groq returned invalid caption JSON."
            )

            raise CaptionGenerationError(
                "json_parse_error",
                "Caption service returned invalid JSON.",
                raw=content[:500],
            ) from exc

    if not isinstance(parsed, dict):
        raise CaptionGenerationError(
            "json_parse_error",
            "Caption service returned JSON in an unexpected format.",
        )

    return parsed


# ---------------------------------------------------------------------------
# Flyer normalization
# ---------------------------------------------------------------------------

def _normalize_flyer(flyer: dict) -> dict:
    """
    Normalize flyer content without inventing product-specific information.

    Features and why_choose_us are limited to three items.
    Contact fields receive editable placeholders when missing.
    """

    flyer = dict(flyer or {})

    features = flyer.get("features")

    if not isinstance(features, list):
        features = []

    flyer["features"] = [
        str(item).strip()
        for item in features[:3]
        if str(item).strip()
    ]

    why_choose_us = flyer.get("why_choose_us")

    if not isinstance(why_choose_us, list):
        why_choose_us = []

    flyer["why_choose_us"] = [
        str(item).strip()
        for item in why_choose_us[:3]
        if str(item).strip()
    ]

    for key, placeholder in DEFAULT_CONTACT_PLACEHOLDERS.items():
        if not str(flyer.get(key) or "").strip():
            flyer[key] = placeholder

    return flyer


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_key(product_data) -> str:
    if isinstance(product_data, str):
        try:
            product_data = json.loads(product_data)
        except (json.JSONDecodeError, TypeError):
            pass

    canonical = json.dumps(
        product_data,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return f"captions_{digest}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_captions(product_data) -> dict:
    """
    Generate flyer content and social captions with one Groq request.

    Pipeline:
        cache → prompt → Groq → JSON parse → normalize → cache

    The function deliberately performs only one provider request per job.
    Retryable failures are surfaced to the outer QStash/job layer.
    """

    cache_key = _cache_key(product_data)

    # Do not make an AI call if the exact product context was already processed.
    cached = get_cached(cache_key)

    if cached is not None:
        logger.info(
            "Caption cache hit: %s",
            cache_key[:16],
        )
        return cached

    # Build prompt before contacting Groq so malformed input fails locally.
    try:
        prompt = build_caption_prompt(product_data)

    except Exception as exc:
        logger.exception(
            "Failed to build caption prompt."
        )

        raise CaptionGenerationError(
            "prompt_error",
            "Could not prepare product information for caption generation.",
        ) from exc

    # Exactly one provider call.
    result = _call_groq(prompt)

    content = _extract_content(result)

    parsed = _parse_captions(content)

    flyer = parsed.get("flyer")

    if isinstance(flyer, dict):
        parsed["flyer"] = _normalize_flyer(flyer)

    # Cache only validated/normalized output.
    set_cached(cache_key, parsed)

    logger.info(
        "Captions generated successfully via %s (product_hash=%s)",
        GROQ_MODEL,
        cache_key[:16],
    )

    return parsed
