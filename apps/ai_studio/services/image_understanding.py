import hashlib
import base64
import json
import logging
import imghdr
import time
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
GEMINI_MAX_RETRIES = getattr(settings, "GEMINI_MAX_RETRIES", 2)
GEMINI_RETRY_BACKOFF_SECONDS = getattr(settings, "GEMINI_RETRY_BACKOFF_SECONDS", 2)

# Gemini status codes worth retrying. Anything else (bad key, bad request) fails fast.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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
#
# It is written as the internal brief a senior creative director + performance
# marketer would produce before a designer ever opens a layout tool. The goal
# is to extract two layers of intelligence:
#
#   1. FACTS  — what the product literally is (feeds copy accuracy)
#   2. DESIRE — why a specific human would stop scrolling, feel something,
#      and buy (feeds emotional resonance + visual direction)
#
# The output also carries enough visual-direction data (palette, mood, focal
# point) that the renderer can make design decisions — not just place text —
# the same way a design system briefs a layout engine. This is what separates
# "AI slapped text on a photo" from something that reads like an agency made it.

_ANALYSIS_PROMPT = """
You are the Head of Creative Strategy at a top-tier brand agency, the kind
that gets hired by companies who want their product to look and feel like
Apple, Glossier, or Nike made it — not like a generic online ad.

Before any designer touches this image, you write the creative brief.
You don't just catalog what the product is. You study it the way a buyer's
eye actually moves across a photo in the first 1.5 seconds — what they
notice first, what makes them feel something, and what would make them
stop scrolling instead of swiping past.

Analyze the attached product image and produce that brief as structured
JSON. Return ONLY valid JSON — no explanation, no markdown, no preamble.

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

  "first_glance": {
    "focal_point": "The exact thing a viewer's eye lands on first (e.g. 'the glossy camera bump catching light')",
    "three_second_read": "What a scrolling buyer concludes about this product in 3 seconds, in their own internal voice — not marketing language (e.g. 'this looks expensive but wearable')",
    "scroll_stopping_element": "The single visual detail worth designing the whole flyer around"
  },

  "visual_direction": {
    "dominant_colors": ["2-4 hex codes actually present in the image, most prominent first"],
    "recommended_palette": ["3-5 hex codes for the flyer background/accents that would flatter and elevate this product — not just repeat its colors"],
    "mood": "2-4 words a designer would use as a mood board caption (e.g. 'clean, confident, editorial')",
    "typography_direction": "What kind of type treatment fits (e.g. 'bold geometric sans, tight tracking, all-caps headline' or 'soft serif, generous spacing, lowercase warmth')",
    "layout_emphasis": "Where the composition should breathe vs. concentrate (e.g. 'large negative space left of product, copy block bottom-right')",
    "lighting_and_texture": "What lighting/texture quality is visible and worth echoing in background design (e.g. 'soft studio light, subtle shadow — avoid busy textures')"
  },

  "headline_directions": [
    {"angle": "status", "line": "A headline built on aspiration/status, under 6 words"},
    {"angle": "problem_solved", "line": "A headline built on solving the buyer's pain point, under 6 words"},
    {"angle": "sensory", "line": "A headline built on how the product looks/feels/performs, under 6 words"}
  ],

  "confidence": "Float 0–1 representing how clearly the product is identifiable"
}

Rules:
- Every field must reflect what is ACTUALLY visible in this specific image — never generic filler that could apply to any product in the category.
- hex codes must be real colors you can see or credibly recommend, not placeholders.
- headline_directions must be three genuinely different angles, not three phrasings of the same idea.
"""

# Keys the downstream caption/renderer pipeline depends on. If Gemini omits
# any of these (partial JSON, truncated response, etc.) we backfill safe
# defaults rather than letting a malformed response break a Celery task.
_REQUIRED_TOP_LEVEL_DEFAULTS = {
    "product_name": None,
    "product_type": None,
    "color_and_finish": None,
    "key_features": [],
    "use_cases": [],
    "lifestyle_tier": "mid_range",
    "emotional_hook": None,
    "desire_statement": None,
    "target_audience": {"primary": None, "pain_point": None, "aspiration": None},
    "scarcity_signals": None,
    "trust_signals": None,
    "price_anchor": None,
    "platform_fit": {"best_platform": "Instagram", "reason": None},
    "first_glance": {
        "focal_point": None,
        "three_second_read": None,
        "scroll_stopping_element": None,
    },
    "visual_direction": {
        "dominant_colors": [],
        "recommended_palette": [],
        "mood": None,
        "typography_direction": None,
        "layout_emphasis": None,
        "lighting_and_texture": None,
    },
    "headline_directions": [],
    "confidence": 0.0,
}


def _apply_defaults(analysis: dict) -> dict:
    """
    Backfill any missing keys with safe defaults so a partial Gemini response
    never crashes the renderer or caption pipeline. Never drops data Gemini
    actually returned — only fills gaps.
    """
    for key, default in _REQUIRED_TOP_LEVEL_DEFAULTS.items():
        if key not in analysis or analysis[key] is None:
            analysis[key] = default
        elif isinstance(default, dict) and isinstance(analysis[key], dict):
            for sub_key, sub_default in default.items():
                analysis[key].setdefault(sub_key, sub_default)
    return analysis


# ─── main function ────────────────────────────────────────────────────────────

def analyze_image(image_bytes: bytes) -> dict:
    """
    Analyze a product image via Gemini Vision.
    Returns structured marketing + visual-direction intelligence for the
    caption and flyer-rendering pipeline.

    Raises ImageAnalysisError on any failure — never returns an error dict.
    Callers (Celery tasks) should catch and decide retry/fail behavior.
    """
    if not image_bytes:
        raise ImageAnalysisError("empty_input", "No image bytes provided")

    # ── cache ────────────────────────────────────────────────────────────────
    cache_key = "analysis_v2_" + hashlib.sha256(image_bytes).hexdigest()
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
            "temperature": 0.4,       # slightly higher than pure extraction —
                                       # headline_directions/mood need creative
                                       # range, structure is still enforced by
                                       # responseMimeType + schema validation
            "responseMimeType": "application/json",
        },
    }

    # ── call Gemini (with retry on transient failures) ─────────────────────────
    response = None
    last_exc = None
    for attempt in range(GEMINI_MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=payload,
                timeout=GEMINI_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Gemini request failed (attempt %d/%d): %s",
                            attempt + 1, GEMINI_MAX_RETRIES + 1, exc)
        else:
            if response.status_code == 200:
                break
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                raise ImageAnalysisError(
                    "api_error",
                    f"Gemini returned {response.status_code}",
                    raw=response.text,
                )
            logger.warning("Gemini returned retryable status %d (attempt %d/%d)",
                            response.status_code, attempt + 1, GEMINI_MAX_RETRIES + 1)

        if attempt < GEMINI_MAX_RETRIES:
            time.sleep(GEMINI_RETRY_BACKOFF_SECONDS * (attempt + 1))

    if response is None:
        logger.exception("Gemini request failed after retries")
        raise ImageAnalysisError("request_error", str(last_exc)) from last_exc

    if response.status_code != 200:
        raise ImageAnalysisError(
            "api_error",
            f"Gemini returned {response.status_code} after retries",
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

    # ── validate / backfill ─────────────────────────────────────────────────────
    analysis = _apply_defaults(analysis)

    # ── cache & return ────────────────────────────────────────────────────────
    result = {"success": True, "analysis": analysis}
    set_cached(cache_key, result)
    logger.info(
        "Image analyzed: %s (confidence=%.2f, mood=%s)",
        analysis.get("product_name"),
        analysis.get("confidence", 0) or 0,
        (analysis.get("visual_direction") or {}).get("mood"),
    )
    return result