import os
from PIL import Image, ImageDraw, ImageFont


DEFAULT_HEADLINE = "Hot Deal!"


def _load_font(size=60):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _get_text(captions, key, fallback=""):
    if not isinstance(captions, dict):
        return fallback
    flyer = captions.get("flyer") or {}
    return str(flyer.get(key) or fallback)


def build_flyer(captions, input_image_path, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        base = Image.open(input_image_path).convert("RGB")
    except Exception as e:
        raise FileNotFoundError(f"Cannot open template image: {e}")

    draw = ImageDraw.Draw(base)

    flyer_data  = captions.get("flyer", {}) if isinstance(captions, dict) else {}

    headline    = str(flyer_data.get("headline")    or "Hot Deal!")
    subheadline = str(flyer_data.get("subheadline") or "")
    cta         = str(flyer_data.get("cta")         or "Shop Now")

    headline_font = _load_font(70)
    sub_font      = _load_font(40)
    cta_font      = _load_font(50)

    draw.text((60, 80),  headline,   fill="white", font=headline_font)
    if subheadline:
        draw.text((60, 180), subheadline, fill="white", font=sub_font)
    draw.text((60, 300), cta, fill="white", font=cta_font)

    try:
        base.save(output_path, format="JPEG", quality=95)
    except Exception as e:
        raise IOError(f"Failed to save flyer: {e}")

    colors = flyer_data.get("colors") or {}

    # ✅ Strip www. prefix — templates add it themselves
    raw_website = str(flyer_data.get("website", "") or "")
    website = raw_website.replace("www.", "").replace("WWW.", "").strip()

    return {
        "output_path": output_path,
        "props": {
            "name":      flyer_data.get("name",      "White Gold"),
            "headline":  headline,
            "subtext":   subheadline,
            "ctaText":   cta,
            "extraText": flyer_data.get("offer",      ""),
            "brandName": flyer_data.get("brand_name", ""),
            "website":   website,                        # ✅ clean, no www.
            "colors": {
                "primary":   colors.get("primary",   "#0a0a0a"),
                "secondary": colors.get("secondary", "#ffffff"),
                "accent":    colors.get("accent",    "#c9a84c"),
            },
        }
    }