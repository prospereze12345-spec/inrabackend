import logging
import tempfile
from pathlib import Path
from typing import Any, Dict

from django.conf import settings
from django.core.files.storage import default_storage
import shutil
from urllib.parse import urlparse

from .renderer import RemotionRenderer, SOCIAL_FORMATS, generate_video

logger = logging.getLogger(__name__)


def _media_relative_path_from_url(url: str) -> str | None:
    """
    Turns a Cloudinary/media URL into the storage-relative key
    (e.g. 'uploads/xxx.png'), so we can hand it to default_storage.open().
    Returns None for blob:/data: URLs, which never resolve to a real file.
    """
    if not url or url.startswith("blob:") or url.startswith("data:"):
        return None

    parsed_path = urlparse(url).path
    # Cloudinary URLs look like /<cloud_name>/image/upload/v123/uploads/xxx.png
    # We only care about everything after the last "/upload/vNNN/" segment.
    if "/upload/" in parsed_path:
        after_upload = parsed_path.split("/upload/", 1)[1]
        # strip a leading version segment like "v1234567890/"
        parts = after_upload.split("/", 1)
        if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
            return parts[1] if len(parts) > 1 else None
        return after_upload

    # fallback: local MEDIA_URL-style path (covers local dev without Cloudinary)
    media_url_path = urlparse(settings.MEDIA_URL).path or "/media/"
    if not parsed_path.startswith(media_url_path):
        return None
    return parsed_path[len(media_url_path):].lstrip("/")


def _copy_asset_to_remotion(media_relative_path: str, subfolder: str) -> str:
    """
    Pulls the file's bytes from whichever storage backend is active
    (local disk in dev, Cloudinary in prod) and writes them into
    remotion/public/<subfolder>/ so Remotion can read them as a
    local asset during rendering. Remotion has no concept of remote
    storage, so this copy step is required regardless of backend.
    """
    try:
        with default_storage.open(media_relative_path, "rb") as src:
            data = src.read()
    except FileNotFoundError:
        logger.warning("Asset not found in storage: %s", media_relative_path)
        return ""
    except Exception as e:
        logger.error("Failed to read %s from storage: %s", media_relative_path, e)
        return ""

    remotion_root = RemotionRenderer._find_project_root()
    dest_dir = remotion_root / "remotion" / "public" / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(media_relative_path).name

    try:
        dest.write_bytes(data)
    except OSError as e:
        logger.error("Failed to write %s: %s", dest, e)
        return ""

    if not dest.is_file():
        logger.error("Copy silently failed, dest missing: %s", dest)
        return ""

    return f"{subfolder}/{dest.name}"


def build_promo_props(job, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fp = dict(job.flyer_props or {})
    captions_block = dict(job.captions or {})

    if overrides:
        override_colors = overrides.get("colors")
        override_captions = overrides.get("captions") or overrides.get("flyer")

        fp.update({k: v for k, v in overrides.items() if k not in ("colors", "captions", "flyer")})

        if override_colors:
            fp["colors"] = {**fp.get("colors", {}), **override_colors}

        if override_captions:
            captions_block["flyer"] = {
                **captions_block.get("flyer", {}),
                **override_captions,
            }

    colors = fp.get("colors", {})
    price_text = fp.get("price") or captions_block.get("flyer", {}).get("price_text", "")

    nobg_uri = ""
    override_image_url = fp.get("productImage")

    if override_image_url:
        rel = _media_relative_path_from_url(override_image_url)
        if rel:
            subfolder = Path(rel).parent.as_posix() or "uploads"
            nobg_uri = _copy_asset_to_remotion(rel, subfolder)
        else:
            nobg_uri = override_image_url

    if not nobg_uri and job.image_nobg:
        # job.image_nobg.name is the storage-relative key regardless of backend
        nobg_uri = _copy_asset_to_remotion(job.image_nobg.name, "nobg")
        if not nobg_uri:
            logger.warning(
                "image_nobg is set on job %s but could not be fetched from storage: %s",
                job.id, job.image_nobg.name,
            )

    return {
        "headline":     fp.get("headline",  ""),
        "subtext":      fp.get("subtext",   ""),
        "ctaText":      fp.get("ctaText",   ""),
        "badgeText":        fp.get("badgeText", ""),
        "templateVariant":  fp.get("templateVariant", ""),
        "templateCategory": fp.get("templateCategory", "Premium Brand"),
        "price":        price_text,
        "brandName":    fp.get("brandName", ""),
        "website":      fp.get("website",   ""),
        "productImage": nobg_uri,
        "colors": {
            "primary":   colors.get("primary",   "#0a0a0a"),
            "secondary": colors.get("secondary", "#ffffff"),
            "accent":    colors.get("accent",    "#c9a84c"),
        },
    }


def resolve_video_format(job) -> str:
    format_name = getattr(job, "video_format", None) or "ig"
    if format_name not in SOCIAL_FORMATS:
        logger.warning(
            "Unknown video_format %r on job %s, falling back to 'ig'",
            format_name, job.id,
        )
        format_name = "ig"
    return format_name


def ensure_job_video(job, verbose: bool = False) -> Path:
    """
    Renders the video to a local temp path (Remotion's output has to land
    somewhere on disk), then uploads the result into default_storage so
    job.video points at Cloudinary like every other field.
    """
    if job.video:
        # existence check now goes through the storage backend, not MEDIA_ROOT
        if default_storage.exists(job.video.name):
            # we still need a local copy for anything downstream that opens
            # job.video as a path (e.g. re-serving for export) — caller
            # decides if it needs bytes; here we just confirm it's there.
            return Path(job.video.name)
        logger.warning(
            "job.video points at %s but it's missing from storage — re-rendering.",
            job.video.name,
        )

    props = build_promo_props(job)
    format_name = resolve_video_format(job)

    with tempfile.TemporaryDirectory() as tmp_dir:
        video_abs = Path(tmp_dir) / f"{job.id}.mp4"

        generate_video(
            props=props,
            output_path=str(video_abs),
            format_name=format_name,
            verbose=verbose,
        )

        from django.core.files.base import ContentFile
        with open(video_abs, "rb") as f:
            job.video.save(f"{job.id}.mp4", ContentFile(f.read()), save=False)
        job.save(update_fields=["video"])

        return video_abs
