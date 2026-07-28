import hashlib
import base64
import json
import logging
import imghdr
from io import BytesIO

import requests
from django.conf import settings

from ..utils.cache import get_cached, set_cached
from .exceptions import ImageAnalysisError

logger = logging.getLogger(__name__)

GEMINI_API_KEY = getattr(settings, "GEMINI_API_KEY", "")
GEMINI_MODEL   = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL     = (
    f"https://generativelanguage.googleapis.com"
    f"/v1beta/models/{GEMINI_MODEL}:generateContent"
)
GEMINI_TIMEOUT = getattr(settings, "GEMINI_TIMEOUT", 120)


_MIME_MAP = {
    "jpeg": "image/jpeg",
    "png":  "image/png",
    "webp": "image/webp",
    "gif":  "image/gif",
}

def _detect_mime(image_bytes: bytes) -> str:
    detected = imghdr.what(BytesIO(image_bytes))
    return _MIME_MAP.get(detected, "image/jpeg")  # safe fallback


# ─── Gemini prompt ───────────────────────────────────────────────────────────
#
# This is not a "describe the image" prompt.
# It extracts the exact marketing intelligence the caption layer needs:
# emotional hooks, lifestyle tier, scarcity signals, audience psychology.
# The better this output, the more the captions sound like a paid agency.

_ANALYSIS_PROMPT = """
You are the Head of Product Intelligence at a top-tier e-commerce marketing firm.
Your job is to deeply analyze this product image and extract structured marketing intelligence.

Return ONLY valid JSON — no explanation, no markdown, no preamble.

{
  "product_name": "Specific product name (e.g. 'Satin Bonnet with Elastic Band', not 'hat')",
  "product_type": "Category (e.g. haircare, fashion, electronics, food, skincare)",
  "color_and_finish": "Exact color + finish (e.g. 'Champagne Gold matte')",
  "key_features": ["3-5 specific visible product features — be precise, not generic"],
  "use_cases": ["2-3 real-world situations this product solves"],

  "lifestyle_tier": "One of: budget_everyday | mid_range | premium | luxury",
  "emotional_hook": "The single strongest emotion this product triggers in a buyer (e.g. confidence, protection, self-care, status, nostalgia)",
  "desire_statement": "Complete this: 'Every [target person] deserves...' — make it aspirational",

  "target_audience": {
    "primary": "Who buys this (be specific: 'Nigerian women 22–38 who care about natural hair')",
    "pain_point": "What problem do they have that this solves?",
    "aspiration": "What do they want to become or feel after buying this?"
  },

  "scarcity_signals": "Any visible cues of limited availability, trending status, or seasonal relevance — or null",
  "trust_signals": "Visible brand marks, quality finishes, certifications, packaging quality — or null",
  "price_anchor": "One of: under_1k | 1k_5k | 5k_20k | 20k_50k | 50k_plus (in Naira)",

  "platform_fit": {
    "best_platform": "Instagram | Facebook | TikTok | WhatsApp",
    "reason": "One sentence why this platform fits this product best"
  },

  "confidence": "Float 0–1 representing how clearly the product is identifiable"
}
"""

# ─── main function ────────────────────────────────────────────────────────────

def analyze_image(image_bytes: bytes) -> dict:
    """
    Analyze a product image via Gemini Vision.
    Returns structured marketing intelligence for the caption pipeline.

    Raises ImageAnalysisError on any failure — never returns an error dict.
    Callers (Celery tasks) should catch and decide retry/fail behavior.
    """
    if not image_bytes:
        raise ImageAnalysisError("empty_input", "No image bytes provided")

    # ── cache ────────────────────────────────────────────────────────────────
    cache_key = "analysis_" + hashlib.sha256(image_bytes).hexdigest()
    cached = get_cached(cache_key)
    if cached:
        return cached

    # ── encode ───────────────────────────────────────────────────────────────
    try:
        mime_type = _detect_mime(image_bytes)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    except Exception as exc:
        raise ImageAnalysisError("encoding_failed", str(exc)) from exc

    # ── build payload ─────────────────────────────────────────────────────────
    payload = {
        "contents": [{
            "parts": [
                {"text": _ANALYSIS_PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,       # low temp = consistent structured output
            "responseMimeType": "application/json",
        },
    }

    # ── call Gemini ───────────────────────────────────────────────────────────
    try:
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            timeout=GEMINI_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception("Gemini request failed")
        raise ImageAnalysisError("request_error", str(exc)) from exc

    if response.status_code != 200:
        raise ImageAnalysisError(
            "api_error",
            f"Gemini returned {response.status_code}",
            raw=response.text,
        )

    # ── extract ───────────────────────────────────────────────────────────────
    try:
        data      = response.json()
        raw_text  = data["candidates"][0]["content"]["parts"][0]["text"]
        analysis  = json.loads(raw_text)
    except (KeyError, IndexError) as exc:
        raise ImageAnalysisError(
            "empty_response", "Unexpected Gemini response shape", raw=response.text
        ) from exc
    except json.JSONDecodeError as exc:
        raise ImageAnalysisError(
            "parse_error", "Model returned non-JSON", raw=raw_text
        ) from exc

    # ── cache & return ────────────────────────────────────────────────────────
    result = {"success": True, "analysis": analysis}
    set_cached(cache_key, result)
    logger.info("Image analyzed: %s (confidence=%.2f)", analysis.get("product_name"), analysis.get("confidence", 0))
    return result
