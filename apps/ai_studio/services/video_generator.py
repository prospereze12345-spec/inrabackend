import logging
import tempfile
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .renderer_dispatch import trigger_github_render
from .renderer import (
    RemotionRenderer,
    SOCIAL_FORMATS,
    generate_video,
)


logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_VOICE_PRESET = "female_us"
DEFAULT_VOICE = "en-US-AriaNeural"

VOICE_PRESETS = {
    "female_us": "en-US-AriaNeural",
    "male_us": "en-US-GuyNeural",
    "female_uk": "en-GB-SoniaNeural",
    "male_uk": "en-GB-RyanNeural",
}

DEFAULT_COLORS = {
    "primary": "#0a0a0a",
    "secondary": "#ffffff",
    "accent": "#c9a84c",
}

DEFAULT_MEDIA_ORIGIN = (
    "https://inrabackend-docker.onrender.com"
)

DEFAULT_RENDER_CONCURRENCY = 2
DEFAULT_X264_PRESET = "fast"


# ============================================================================
# GENERAL HELPERS
# ============================================================================

def _clean_string(value: Any) -> str:
    """
    Safely normalize arbitrary input into a trimmed string.
    """
    if value is None:
        return ""

    return str(value).strip()


def _clean_list(
    value: Any,
    limit: int = 5,
) -> list[str]:
    """
    Normalize flyer list data.

    Supports:

        ["Fast delivery", "Premium quality"]

    or:

        "Fast delivery"

    or:

        None
    """
    if value is None:
        return []

    if not isinstance(value, list):
        value = [value]

    result: list[str] = []

    for item in value:
        cleaned = _clean_string(item)

        if cleaned:
            result.append(cleaned)

    return result[:limit]


def _safe_float(
    value: Any,
    default: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    """
    Safely parse a bounded float.
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default

    return max(
        minimum,
        min(maximum, parsed),
    )


# ============================================================================
# MEDIA HELPERS
# ============================================================================

def _storage_url(file_field) -> str:
    """
    Resolve a Django storage file into its public URL.

    Compatible with Django storage backends such as:

        - local filesystem
        - Cloudinary
        - S3
        - other Django storage implementations
    """
    if not file_field:
        return ""

    try:
        return str(
            default_storage.url(
                file_field.name
            )
        )
    except Exception as exc:
        logger.warning(
            "Could not resolve storage URL for %s: %s",
            getattr(
                file_field,
                "name",
                "unknown",
            ),
            exc,
        )
        return ""


def _resolve_media_value(
    value: Any,
) -> str:
    """
    Normalize a media reference.

    Supported:

        https://...
        http://...
        /media/file.png
        media/file.png
        storage/path/file.png

    Remote URLs are preserved.

    Relative storage paths are resolved through
    Django's configured storage backend.
    """
    value = _clean_string(value)

    if not value:
        return ""

    # Browser-only temporary references should not
    # normally reach GitHub rendering, but preserve them
    # for backwards compatibility.
    if value.startswith(
        ("blob:", "data:")
    ):
        return value

    # Already public.
    if value.startswith(
        ("http://", "https://")
    ):
        return value

    public_base_url = _clean_string(
        getattr(
            settings,
            "PUBLIC_BASE_URL",
            "",
        )
    ).rstrip("/")

    # /media/file.png
    if value.startswith("/media/"):
        if public_base_url:
            return (
                f"{public_base_url}"
                f"{value}"
            )

        return value

    # media/file.png
    if value.startswith("media/"):
        if public_base_url:
            return (
                f"{public_base_url}/"
                f"{value}"
            )

        return f"/{value}"

    # Storage key.
    try:
        resolved = str(
            default_storage.url(value)
        )

        # Some storage backends may return a relative
        # URL. Make it public if possible.
        if (
            resolved.startswith("/")
            and public_base_url
        ):
            return (
                f"{public_base_url}"
                f"{resolved}"
            )

        return resolved

    except Exception as exc:
        logger.debug(
            "Could not resolve media value %r: %s",
            value,
            exc,
        )

        return value


def _media_relative_path_from_url(
    url: str,
) -> str | None:
    """
    Convert a storage URL back into a storage-relative path.

    Examples:

        /media/uploads/product.png
            -> uploads/product.png

        Cloudinary:
        /image/upload/v123/uploads/product.png
            -> uploads/product.png

    Returns None for:

        - blob URLs
        - data URLs
        - unrelated external URLs
    """
    url = _clean_string(url)

    if not url or url.startswith(
        ("blob:", "data:")
    ):
        return None

    parsed_path = urlparse(url).path

    # ------------------------------------------------------------------
    # Cloudinary
    # ------------------------------------------------------------------

    if "/upload/" in parsed_path:
        after_upload = parsed_path.split(
            "/upload/",
            1,
        )[1]

        parts = after_upload.split(
            "/",
            1,
        )

        if (
            parts
            and parts[0].startswith("v")
            and parts[0][1:].isdigit()
        ):
            return (
                parts[1]
                if len(parts) > 1
                else None
            )

        return after_upload

    # ------------------------------------------------------------------
    # Django MEDIA_URL
    # ------------------------------------------------------------------

    media_url_path = (
        urlparse(
            getattr(
                settings,
                "MEDIA_URL",
                "/media/",
            )
        ).path
        or "/media/"
    )

    if parsed_path.startswith(
        media_url_path
    ):
        return parsed_path[
            len(media_url_path):
        ].lstrip("/")

    return None


def _copy_asset_to_remotion(
    media_relative_path: str,
    subfolder: str,
) -> str:
    """
    Copy a storage asset into Remotion's public directory.

    This is retained for local-render compatibility.

    GitHub Actions rendering should normally use public
    media URLs instead of copying Django storage files.
    """
    media_relative_path = _clean_string(
        media_relative_path
    )

    if not media_relative_path:
        return ""

    try:
        with default_storage.open(
            media_relative_path,
            "rb",
        ) as source:
            data = source.read()

    except FileNotFoundError:
        logger.warning(
            "Storage asset not found: %s",
            media_relative_path,
        )
        return ""

    except Exception as exc:
        logger.error(
            "Failed reading storage asset %s: %s",
            media_relative_path,
            exc,
        )
        return ""

    remotion_root = (
        RemotionRenderer._find_project_root()
    )

    public_dir = (
        remotion_root
        / "public"
        / subfolder
    )

    public_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = Path(
        media_relative_path
    ).name

    destination = (
        public_dir / filename
    )

    try:
        destination.write_bytes(data)

    except OSError as exc:
        logger.error(
            "Failed writing Remotion asset %s: %s",
            destination,
            exc,
        )
        return ""

    if not destination.is_file():
        logger.error(
            "Remotion asset was not created: %s",
            destination,
        )
        return ""

    return (
        f"{subfolder}/{filename}"
    )


# ============================================================================
# PUBLIC MEDIA ORIGIN
# ============================================================================

def resolve_public_media_origin() -> str:
    """
    Resolve the public backend origin used by Remotion.

    Priority:

        PUBLIC_BASE_URL
        REMOTION_MEDIA_ORIGIN
        DEFAULT_MEDIA_ORIGIN
    """
    candidates = [
        getattr(
            settings,
            "PUBLIC_BASE_URL",
            "",
        ),
        getattr(
            settings,
            "REMOTION_MEDIA_ORIGIN",
            "",
        ),
        DEFAULT_MEDIA_ORIGIN,
    ]

    for candidate in candidates:
        candidate = _clean_string(
            candidate
        )

        if candidate:
            return candidate.rstrip("/")

    return DEFAULT_MEDIA_ORIGIN


# ============================================================================
# MARKETING NARRATION
# ============================================================================

def _sentence(value: str) -> str:
    """
    Normalize marketing copy into a sentence.
    """
    value = _clean_string(value)

    if not value:
        return ""

    if value[-1] in ".!?":
        return value

    return f"{value}."


def build_voiceover_script(
    *,
    brand_name: str,
    headline: str,
    subtext: str,
    features: list[str],
    why_choose_us: list[str],
    price: str,
    cta_text: str,
) -> str:
    """
    Build concise marketing narration.

    Structure:

        HOOK
          ↓
        VALUE
          ↓
        FEATURES
          ↓
        BENEFITS
          ↓
        PRICE
          ↓
        CTA
    """
    parts: list[str] = []

    # ------------------------------------------------------------------
    # HOOK
    # ------------------------------------------------------------------

    if brand_name and headline:
        parts.append(
            f"Meet {brand_name} — "
            f"{_sentence(headline)}"
        )

    elif headline:
        parts.append(
            _sentence(headline)
        )

    elif brand_name:
        parts.append(
            f"Discover {brand_name}."
        )

    # ------------------------------------------------------------------
    # VALUE
    # ------------------------------------------------------------------

    if subtext:
        parts.append(
            _sentence(subtext)
        )

    # ------------------------------------------------------------------
    # FEATURES
    # ------------------------------------------------------------------

    if features:
        feature_text = ", ".join(
            features[:3]
        )

        if len(features) == 1:
            parts.append(
                f"Designed with {feature_text}."
            )
        else:
            parts.append(
                f"Enjoy {feature_text}, "
                f"all designed to give you "
                f"a better experience."
            )

    # ------------------------------------------------------------------
    # WHY CHOOSE US
    # ------------------------------------------------------------------

    if why_choose_us:
        benefits = ", ".join(
            why_choose_us[:3]
        )

        parts.append(
            f"Why settle for less? "
            f"You get {benefits}."
        )

    # ------------------------------------------------------------------
    # PRICE
    # ------------------------------------------------------------------

    if price:
        parts.append(
            f"Get yours today for {price}."
        )

    # ------------------------------------------------------------------
    # CTA
    # ------------------------------------------------------------------

    if cta_text:
        parts.append(
            _sentence(cta_text)
        )
    else:
        parts.append(
            "Order now and experience "
            "the difference."
        )

    return " ".join(
        part.strip()
        for part in parts
        if part and part.strip()
    ).strip()


def _resolve_voice(
    flyer_props: Dict[str, Any],
) -> str:
    """
    Resolve a supported voice preset.

    Explicit voiceoverVoice takes priority for backwards
    compatibility.
    """
    explicit_voice = _clean_string(
        flyer_props.get(
            "voiceoverVoice"
        )
        or flyer_props.get(
            "voiceover_voice"
        )
    )

    if explicit_voice:
        return explicit_voice

    preset = _clean_string(
        flyer_props.get(
            "voicePreset"
        )
    ) or DEFAULT_VOICE_PRESET

    return VOICE_PRESETS.get(
        preset,
        DEFAULT_VOICE,
    )


# ============================================================================
# PROMO PROPS
# ============================================================================

def build_promo_props(
    job,
    overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build the canonical PromoVideo props.

    This is the single contract between Django and
    PromoVideo.tsx.
    """

    # ------------------------------------------------------------------
    # BASE DATA
    # ------------------------------------------------------------------

    fp = dict(
        getattr(
            job,
            "flyer_props",
            None,
        )
        or {}
    )

    captions_block = dict(
        getattr(
            job,
            "captions",
            None,
        )
        or {}
    )

    flyer = dict(
        captions_block.get(
            "flyer"
        )
        or {}
    )

    # ------------------------------------------------------------------
    # OVERRIDES
    # ------------------------------------------------------------------

    if overrides:
        overrides = dict(
            overrides
        )

        override_colors = dict(
            overrides.get(
                "colors"
            )
            or {}
        )

        override_captions = dict(
            overrides.get(
                "captions"
            )
            or overrides.get(
                "flyer"
            )
            or {}
        )

        for key, value in overrides.items():
            if key not in {
                "colors",
                "captions",
                "flyer",
            }:
                fp[key] = value

        if override_colors:
            fp["colors"] = {
                **dict(
                    fp.get("colors")
                    or {}
                ),
                **override_colors,
            }

        if override_captions:
            flyer = {
                **flyer,
                **override_captions,
            }

    # ------------------------------------------------------------------
    # TEXT
    # ------------------------------------------------------------------

    headline = _clean_string(
        fp.get("headline")
        or flyer.get("headline")
    )

    subtext = _clean_string(
        fp.get("subtext")
        or flyer.get("subtext")
    )

    cta_text = _clean_string(
        fp.get("ctaText")
        or flyer.get("ctaText")
        or flyer.get("cta")
    )

    price_text = _clean_string(
        fp.get("price")
        or flyer.get("price_text")
        or flyer.get("price")
    )

    brand_name = _clean_string(
        fp.get("brandName")
        or flyer.get("brandName")
        or "Premium Brand"
    )

    website = _clean_string(
        fp.get("website")
        or flyer.get("website")
    )

    phone = _clean_string(
        fp.get("phone")
        or flyer.get("phone")
    )

    email = _clean_string(
        fp.get("email")
        or flyer.get("email")
    )

    # ------------------------------------------------------------------
    # FEATURES
    # ------------------------------------------------------------------

    features = _clean_list(
        fp.get("features")
        or flyer.get("features")
        or [],
        limit=5,
    )

    # ------------------------------------------------------------------
    # WHY CHOOSE US
    # ------------------------------------------------------------------

    why_choose_us = _clean_list(
        fp.get("whyChooseUs")
        or fp.get("why_choose_us")
        or flyer.get("whyChooseUs")
        or flyer.get("why_choose_us")
        or [],
        limit=5,
    )

    # ------------------------------------------------------------------
    # COLORS
    # ------------------------------------------------------------------

    colors = dict(
        fp.get("colors")
        or {}
    )

    normalized_colors = {
        "primary": (
            _clean_string(
                colors.get(
                    "primary",
                    DEFAULT_COLORS["primary"],
                )
            )
            or DEFAULT_COLORS["primary"]
        ),
        "secondary": (
            _clean_string(
                colors.get(
                    "secondary",
                    DEFAULT_COLORS["secondary"],
                )
            )
            or DEFAULT_COLORS["secondary"]
        ),
        "accent": (
            _clean_string(
                colors.get(
                    "accent",
                    DEFAULT_COLORS["accent"],
                )
            )
            or DEFAULT_COLORS["accent"]
        ),
    }

    # ------------------------------------------------------------------
    # PRODUCT IMAGE
    # ------------------------------------------------------------------

    product_image = ""

    override_product_image = _clean_string(
        fp.get("productImage")
    )

    if override_product_image:
        product_image = _resolve_media_value(
            override_product_image
        )

    elif getattr(
        job,
        "image_nobg",
        None,
    ):
        product_image = _storage_url(
            job.image_nobg
        )

    # ------------------------------------------------------------------
    # LOGO
    # ------------------------------------------------------------------

    logo_image = _clean_string(
        fp.get("logoImage")
        or fp.get("logo")
    )

    if logo_image:
        logo_image = _resolve_media_value(
            logo_image
        )

    # ------------------------------------------------------------------
    # BADGE
    # ------------------------------------------------------------------

    badge = fp.get("badge")

    if not isinstance(
        badge,
        dict,
    ):
        badge = None

    else:
        transform = dict(
            badge.get("transform")
            or {}
        )

        badge = {
            "visible": bool(
                badge.get(
                    "visible",
                    True,
                )
            ),
            "text": _clean_string(
                badge.get("text")
                or fp.get("badgeText")
            ),
            "subText": (
                _clean_string(
                    badge.get("subText")
                    or badge.get("sub_text")
                    or "LIMITED OFFER"
                )
            ),
            "textColor": (
                _clean_string(
                    badge.get(
                        "textColor",
                        "#ffffff",
                    )
                )
                or "#ffffff"
            ),
            "bgColor": (
                _clean_string(
                    badge.get(
                        "bgColor",
                        normalized_colors["accent"],
                    )
                )
                or normalized_colors["accent"]
            ),
            "transform": {
                "x": _safe_float(
                    transform.get(
                        "x",
                        82,
                    ),
                    default=82,
                    minimum=-500,
                    maximum=500,
                ),
                "y": _safe_float(
                    transform.get(
                        "y",
                        18,
                    ),
                    default=18,
                    minimum=-500,
                    maximum=500,
                ),
                "scale": _safe_float(
                    transform.get(
                        "scale",
                        1,
                    ),
                    default=1,
                    minimum=0.1,
                    maximum=5,
                ),
            },
        }

    # =========================================================================
    # VOICEOVER
    # =========================================================================

    voiceover_text = _clean_string(
        fp.get("voiceoverText")
        or fp.get("voiceover_text")
    )

    if not voiceover_text:
        voiceover_text = build_voiceover_script(
            brand_name=brand_name,
            headline=headline,
            subtext=subtext,
            features=features,
            why_choose_us=why_choose_us,
            price=price_text,
            cta_text=cta_text,
        )

    voice_preset = _clean_string(
        fp.get("voicePreset")
        or fp.get("voice_preset")
        or DEFAULT_VOICE_PRESET
    )

    if voice_preset not in VOICE_PRESETS:
        voice_preset = DEFAULT_VOICE_PRESET

    voiceover_voice = _resolve_voice(fp)

    voiceover_url = _clean_string(
        fp.get("voiceoverUrl")
        or fp.get("voiceover_url")
    )

    if voiceover_url:
        voiceover_url = _resolve_media_value(
            voiceover_url
        )

    # =========================================================================
    # BACKGROUND MUSIC
    # =========================================================================

    music_url = _clean_string(
        fp.get("musicUrl")
        or fp.get("music_url")
    )

    if music_url:
        music_url = _resolve_media_value(
            music_url
        )

    music_volume = _safe_float(
        fp.get(
            "musicVolume",
            fp.get(
                "music_volume",
                0.12,
            ),
        ),
        default=0.12,
        minimum=0.0,
        maximum=1.0,
    )

    # =========================================================================
    # FINAL REMOTION CONTRACT
    # =========================================================================

    props: Dict[str, Any] = {
        # Core content
        "headline": headline,
        "subtext": subtext,
        "ctaText": cta_text,
        "price": price_text,

        # Brand
        "brandName": brand_name,
        "website": website,
        "phone": phone,
        "email": email,

        # Images
        "productImage": product_image,
        "logoImage": logo_image,

        # Marketing
        "features": features,
        "whyChooseUs": why_choose_us,

        # Design
        "colors": normalized_colors,
        "badge": badge,

        # Voiceover
        "voicePreset": voice_preset,
        "voiceoverVoice": voiceover_voice,
        "voiceoverText": voiceover_text,
        "voiceoverUrl": voiceover_url,

        # Music
        "musicUrl": music_url,
        "musicVolume": music_volume,

        # Template metadata
        "templateVariant": _clean_string(
            fp.get("templateVariant")
        ),
        "templateCategory": (
            _clean_string(
                fp.get(
                    "templateCategory",
                    "Premium Brand",
                )
            )
            or "Premium Brand"
        ),
    }

    logger.info(
        "Built PromoVideo props | "
        "job=%s | features=%d | benefits=%d | "
        "voice=%s | voicePreset=%s | music=%s",
        getattr(
            job,
            "id",
            "unknown",
        ),
        len(features),
        len(why_choose_us),
        voiceover_voice,
        voice_preset,
        bool(music_url),
    )

    return props


# ============================================================================
# VIDEO FORMAT
# ============================================================================

def resolve_video_format(
    job,
) -> str:
    """
    Resolve the requested social-video format.

    Falls back safely to Instagram portrait.
    """
    format_name = (
        getattr(
            job,
            "video_format",
            None,
        )
        or "ig"
    )

    format_name = _clean_string(
        format_name
    ).lower()

    if format_name not in SOCIAL_FORMATS:
        logger.warning(
            "Unknown video_format %r for job %s. "
            "Falling back to ig.",
            format_name,
            getattr(
                job,
                "id",
                "unknown",
            ),
        )

        return "ig"

    return format_name


# ============================================================================
# GITHUB ACTIONS RENDER
# ============================================================================

def dispatch_job_video(
    job,
) -> None:
    """
    Dispatch a video render to GitHub Actions.

    Pipeline:

        Django
          ↓
        build_promo_props()
          ↓
        GitHub Actions
          ↓
        render.mjs
          ├── TTS
          ├── bundle PromoVideo
          ├── select composition
          ├── render MP4
          └── validate output
          ↓
        Cloudinary / Django storage
          ↓
        completion webhook
    """

    # ------------------------------------------------------------------
    # Prevent duplicate rendering
    # ------------------------------------------------------------------

    existing_video = getattr(
        job,
        "video",
        None,
    )

    if (
        existing_video
        and getattr(
            existing_video,
            "name",
            "",
        )
    ):
        try:
            if default_storage.exists(
                existing_video.name
            ):
                logger.info(
                    "Job %s already has a rendered video.",
                    job.id,
                )
                return
        except Exception as exc:
            logger.warning(
                "Could not check existing video for job %s: %s",
                job.id,
                exc,
            )

    # ------------------------------------------------------------------
    # Canonical props
    # ------------------------------------------------------------------

    props = build_promo_props(job)

    # ------------------------------------------------------------------
    # Social format
    # ------------------------------------------------------------------

    format_name = resolve_video_format(job)

    format_config = SOCIAL_FORMATS[
        format_name
    ]

    # ------------------------------------------------------------------
    # Public media origin
    # ------------------------------------------------------------------

    media_origin = (
        resolve_public_media_origin()
    )

    # ------------------------------------------------------------------
    # GitHub render configuration
    # ------------------------------------------------------------------

    config = {
        "compositionId": "PromoVideo",

        "inputProps": props,

        "width": int(
            format_config.width
        ),

        "height": int(
            format_config.height
        ),

        "fps": int(
            format_config.fps
        ),

        "durationInFrames": int(
            format_config.duration
        ),

        "outputPath": (
            f"/tmp/render-output/"
            f"{job.id}.mp4"
        ),

        "mediaOrigin": media_origin,

        "jobId": str(
            job.id
        ),

        # Rendering performance.
        #
        # Keep this conservative because GitHub-hosted
        # rendering should remain stable rather than trying
        # to maximize parallelism.
        "concurrency": int(
            getattr(
                settings,
                "REMOTION_RENDER_CONCURRENCY",
                DEFAULT_RENDER_CONCURRENCY,
            )
        ),

        "x264Preset": getattr(
            settings,
            "REMOTION_X264_PRESET",
            DEFAULT_X264_PRESET,
        ),
    }

    logger.info(
        "Dispatching job %s to GitHub | "
        "format=%s | resolution=%sx%s | "
        "fps=%s | duration=%s frames | "
        "mediaOrigin=%s | voice=%s | "
        "preset=%s | music=%s",
        job.id,
        format_name,
        format_config.width,
        format_config.height,
        format_config.fps,
        format_config.duration,
        media_origin,
        props.get(
            "voiceoverVoice"
        ),
        props.get(
            "voicePreset"
        ),
        bool(
            props.get(
                "musicUrl"
            )
        ),
    )

    trigger_github_render(
        job_id=str(
            job.id
        ),
        config=config,
    )


# ============================================================================
# LOCAL / FALLBACK RENDER
# ============================================================================

def ensure_job_video(
    job,
    verbose: bool = False,
) -> Path:
    """
    Render a video locally when required.

    The rendered file is uploaded through Django storage.

    The returned Path points to the stored object name,
    not the temporary file.
    """

    # ------------------------------------------------------------------
    # Existing video
    # ------------------------------------------------------------------

    existing_video = getattr(
        job,
        "video",
        None,
    )

    if (
        existing_video
        and getattr(
            existing_video,
            "name",
            "",
        )
    ):
        try:
            if default_storage.exists(
                existing_video.name
            ):
                logger.info(
                    "Job %s already has video: %s",
                    job.id,
                    existing_video.name,
                )

                return Path(
                    existing_video.name
                )

        except Exception as exc:
            logger.warning(
                "Could not verify existing video for job %s: %s",
                job.id,
                exc,
            )

    # ------------------------------------------------------------------
    # Canonical props
    # ------------------------------------------------------------------

    props = build_promo_props(job)

    # ------------------------------------------------------------------
    # Social format
    # ------------------------------------------------------------------

    format_name = resolve_video_format(job)

    # ------------------------------------------------------------------
    # Temporary local render
    # ------------------------------------------------------------------

    with tempfile.TemporaryDirectory() as tmp_dir:

        video_abs = (
            Path(tmp_dir)
            / f"{job.id}.mp4"
        )

        logger.info(
            "Locally rendering job %s | "
            "format=%s | resolution=%sx%s | "
            "voice=%s",
            job.id,
            format_name,
            SOCIAL_FORMATS[
                format_name
            ].width,
            SOCIAL_FORMATS[
                format_name
            ].height,
            props.get(
                "voiceoverVoice"
            ),
        )

        generate_video(
            props=props,
            output_path=str(
                video_abs
            ),
            format_name=format_name,
            verbose=verbose,
        )

        # ------------------------------------------------------------------
        # Verify render output
        # ------------------------------------------------------------------

        if not video_abs.is_file():
            raise RuntimeError(
                "Remotion completed but did not "
                f"create the output file: "
                f"{video_abs}"
            )

        file_size = video_abs.stat().st_size

        if file_size <= 0:
            raise RuntimeError(
                "Remotion created an empty "
                f"video file: {video_abs}"
            )

        logger.info(
            "Local Remotion render completed | "
            "job=%s | size=%.2f MB",
            job.id,
            file_size / 1024 / 1024,
        )

        # ------------------------------------------------------------------
        # Upload through Django storage
        # ------------------------------------------------------------------

        with video_abs.open(
            "rb"
        ) as video_file:

            job.video.save(
                f"{job.id}.mp4",
                ContentFile(
                    video_file.read()
                ),
                save=False,
            )

        job.save(
            update_fields=[
                "video"
            ]
        )

        logger.info(
            "Job %s video uploaded successfully: %s",
            job.id,
            job.video.name,
        )

        # TemporaryDirectory deletes video_abs
        # immediately after this block.
        return Path(
            job.video.name
        )
