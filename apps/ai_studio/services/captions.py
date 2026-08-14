import json
import hashlib
import logging

import requests
from requests.adapters import HTTPAdapter, Retry
from django.conf import settings

from ..utils.cache import get_cached, set_cached
from ..prompts.caption_prompt import build_caption_prompt
from ..grok_client import GROQ_URL, HEADERS

logger = logging.getLogger(__name__)



GROQ_MODEL   = getattr(settings, "GROQ_CAPTION_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT = getattr(settings, "GROQ_REQUEST_TIMEOUT", 120)

DEFAULT_CONTACT_PLACEHOLDERS = {
    "phone":   "+234 800 000 0000",
    "email":   "hello@yourbrand.com",
    "website": "www.yourbrand.com",
}


class CaptionGenerationError(Exception):
    RETRYABLE_STAGES = {"request_error", "api_error"}

    def __init__(self, stage: str, message: str, raw=None):
        self.stage = stage
        self.raw   = raw
        super().__init__(f"[{stage}] {message}")

  
    def __reduce__(self):
        return (self.__class__, (self.stage, str(self), self.raw))

    @property
    def is_retryable(self) -> bool:
        return self.stage in self.RETRYABLE_STAGES



def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.6,                        
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session



_SYSTEM_PROMPT = """
You are the Chief Marketing Officer of Africa's #1 social commerce growth agency.
You have generated copy for brands on Amazon, Jumia, Konga, eBay, and Shopify.

Your sole job is to write HIGH-CONVERTING social media captions and marketing copy
that drives real sales — DMs, WhatsApp inquiries, and purchases — especially for
small businesses with under 500 followers who need every post to work hard.

You understand African buyer psychology deeply:
- WhatsApp is a sales channel, not just messaging
- Price visibility builds trust, not skepticism
- Scarcity and urgency work when they feel real
- The caption must sell the product AND the seller

Output rules (non-negotiable):
- Return ONLY valid JSON — no markdown, no explanation, no preamble
- Every caption must be ready to post — no placeholders, no templates
- Match each platform's native tone and culture exactly
- Make every word earn its place
"""


def _call_groq(prompt: str) -> dict:
    payload = {
    "model": GROQ_MODEL,
    "messages": [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ],
    "temperature": 0.2,
    "max_tokens": 1500,
    "response_format": {"type": "json_object"},
}

    session = _build_session()

    try:
        response = session.post(
            GROQ_URL,
            headers=HEADERS,
            json=payload,
            timeout=GROQ_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception("Groq request failed")
        raise CaptionGenerationError("request_error", str(exc)) from exc

    if response.status_code != 200:
        raise CaptionGenerationError(
            "api_error",
            f"Groq returned HTTP {response.status_code}",
            raw=response.text,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise CaptionGenerationError(
            "invalid_json_response", str(exc), raw=response.text
        ) from exc



def _extract_content(result: dict) -> str:
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CaptionGenerationError(
            "malformed_response",
            f"Unexpected Groq response shape: {type(exc).__name__}",
            raw=result,
        ) from exc

    if not content or not content.strip():
        raise CaptionGenerationError(
            "empty_content", "Model returned empty content", raw=result
        )

    return content


def _parse_captions(content: str) -> dict:
    content = content.strip()

    if content.startswith("```json"):
        content = content[7:]

    if content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        return json.loads(content[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        logger.exception("Bad captions JSON:\n%s", content)

        raise CaptionGenerationError(
            "json_parse_error",
            "Could not parse captions JSON from model output",
            raw=content[:1000],
        ) from exc


def _normalize_flyer(flyer: dict) -> dict:
    """
    Flyer-content-only normalization (captions/hashtags/hook_variants are
    left untouched). Guarantees:
      - features / why_choose_us are always lists, capped at exactly 3 items
      - phone / email / website always have a value — the model's own
        output if present, otherwise a generic editable placeholder — so
        the editor's Content tab (Phone/Email/Website toggles) always has
        something to show, and the user can edit or delete it freely.
    """
    flyer = dict(flyer or {})

    features = flyer.get("features")
    if not isinstance(features, list):
        features = []
    flyer["features"] = [str(f).strip() for f in features[:3] if str(f).strip()]

    why = flyer.get("why_choose_us")
    if not isinstance(why, list):
        why = []
    flyer["why_choose_us"] = [str(w).strip() for w in why[:3] if str(w).strip()]

    for key, placeholder in DEFAULT_CONTACT_PLACEHOLDERS.items():
        if not str(flyer.get(key) or "").strip():
            flyer[key] = placeholder

    return flyer


def _cache_key(product_data) -> str:
    if isinstance(product_data, str):
        try:
            product_data = json.loads(product_data)
        except (json.JSONDecodeError, TypeError):
            pass

    canonical = json.dumps(product_data, sort_keys=True, ensure_ascii=False, default=str)
    digest    = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"captions_{digest}"



def generate_captions(product_data) -> dict:
    """
    Generate high-converting flyer content + social media captions via Groq
    (single call — see build_caption_prompt).

    Args:
        product_data: dict or JSON string from the Gemini image analysis pipeline.

    Returns:
        Parsed dict with keys: flyer, captions, hashtags, hook_variants.
        flyer.features / flyer.why_choose_us / flyer.phone / flyer.email /
        flyer.website are guaranteed present after normalization.

    Raises:
        CaptionGenerationError: on any failure.
        Check exc.is_retryable to decide whether the Celery task should retry.
    """
    cache_key = _cache_key(product_data)

    cached = get_cached(cache_key)
    if cached:
        logger.debug("Caption cache hit: %s", cache_key[:16])
        return cached

    prompt  = build_caption_prompt(product_data)
    result  = _call_groq(prompt)
    content = _extract_content(result)
    logger.error("RAW GROQ OUTPUT:\n%s", content)
    parsed  = _parse_captions(content)

    if isinstance(parsed.get("flyer"), dict):
        parsed["flyer"] = _normalize_flyer(parsed["flyer"])

    set_cached(cache_key, parsed)

    logger.info(
        "Captions generated via %s (product_hash=%s)",
        GROQ_MODEL, cache_key[:16],
    )

    return parsed