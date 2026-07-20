import logging
from pathlib import Path
from typing import Any, Dict

from django.conf import settings
import shutil
from urllib.parse import urlparse

from .renderer import RemotionRenderer, SOCIAL_FORMATS, generate_video  # already there
from .renderer import RemotionRenderer, SOCIAL_FORMATS, generate_video  # noqa: F401

logger = logging.getLogger(__name__)



def _media_relative_path_from_url(url: str) -> str | None:
    """
    Turns 'http://host/media/uploads/xxx.png' into 'uploads/xxx.png'.
    Returns None for blob:/data:/external URLs we can't resolve to a
    local file (blob: is a browser-only in-memory URL and will never
    be reachable here; data: and unrelated external URLs are skipped
    too, since we only know how to copy from our own MEDIA_ROOT).
    """
    if not url or url.startswith("blob:") or url.startswith("data:"):
        return None
    media_url_path = urlparse(settings.MEDIA_URL).path or "/media/"
    parsed_path = urlparse(url).path
    if not parsed_path.startswith(media_url_path):
        return None
    return parsed_path[len(media_url_path):].lstrip("/")


def _copy_asset_to_remotion(media_relative_path: str, subfolder: str) -> str:
    src_abs = Path(settings.MEDIA_ROOT) / media_relative_path
    if not src_abs.is_file():
        logger.warning("Asset not found on disk: %s", src_abs)
        return ""

    remotion_root = RemotionRenderer._find_project_root()
    dest_dir = remotion_root / "remotion" / "public" / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src_abs.name

    try:
        shutil.copy2(src_abs, dest)
    except OSError as e:
        logger.error("Failed to copy %s -> %s: %s", src_abs, dest, e)
        return ""

    if not dest.is_file():
        logger.error("Copy silently failed, dest missing: %s", dest)
        return ""

    return f"{subfolder}/{src_abs.name}"

def build_promo_props(job, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Single source of truth for the props passed into the PromoVideo
    composition.

    Both the background Celery pipeline (stage 6) and the on-demand
    /export endpoint call this. Previously they built props two
    different ways — stage 6 pulled from job.flyer_props / job.captions,
    while ExportPackageView pulled from separate scalar columns
    (job.headline, job.primary_color, job.png, ...) that the pipeline
    never actually populates. That's why exports could come out with
    blank/stale text and colors, or blow up outright on the missing
    job.png attribute. Now there is exactly one place this data comes
    from.

    `overrides`, if provided, represents live in-browser edits that
    haven't been saved to the job yet (e.g. a user tweaking text/colors
    in the editor and downloading before hitting save). When present,
    it's merged on top of the job's persisted flyer_props/captions so
    the render reflects what the user currently sees on screen rather
    than the last-saved state.
    """
    fp = dict(job.flyer_props or {})
    captions_block = dict(job.captions or {})

    if overrides:
        # overrides may itself carry a "colors" sub-dict and/or a
        # "captions"/"flyer" sub-block — merge shallowly so unspecified
        # keys still fall back to the persisted job state.
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
       nobg_abs = Path(settings.MEDIA_ROOT) / str(job.image_nobg)
       if nobg_abs.is_file():
         nobg_uri = _copy_asset_to_remotion(str(job.image_nobg), "nobg")
       else:
        logger.warning(
            "image_nobg is set on job %s but file is missing on disk: %s",
            job.id, nobg_abs,
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
    """Format must match one of RemotionRenderer's SOCIAL_FORMATS keys."""
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
    Render (or reuse) the promo video for a job.

    Safe to call from both the Celery pipeline and the export endpoint:
    if job.video already points at a file that exists on disk, it's
    returned as-is with no re-render. Otherwise it renders using
    build_promo_props(), so the export button and the background job
    are guaranteed to produce the same video.
    """
    if job.video:
        existing = Path(settings.MEDIA_ROOT) / str(job.video)
        if existing.is_file():
            return existing
        logger.warning(
            "job.video points at %s but the file is missing — re-rendering.",
            existing,
        )

    video_abs = Path(settings.MEDIA_ROOT) / "videos" / f"{job.id}.mp4"
    props = build_promo_props(job)
    format_name = resolve_video_format(job)

    generate_video(
        props=props,
        output_path=str(video_abs),
        format_name=format_name,
        verbose=verbose,
    )

    job.video = f"videos/{job.id}.mp4"
    job.save(update_fields=["video"])
    return video_abs