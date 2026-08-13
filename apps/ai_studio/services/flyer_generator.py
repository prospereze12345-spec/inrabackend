import os


DEFAULT_HEADLINE = "Hot Deal!"


def _get_flyer_data(captions):
    """
    Safely extract the flyer object from generated caption data.
    """
    if not isinstance(captions, dict):
        return {}

    flyer = captions.get("flyer")

    if not isinstance(flyer, dict):
        return {}

    return flyer


def _clean_string(value, fallback=""):
    if value is None:
        return fallback

    return str(value).strip()


def _clean_list(value):
    """
    Always return a clean list of strings.
    """
    if not isinstance(value, list):
        return []

    return [
        str(item).strip()
        for item in value
        if item is not None and str(item).strip()
    ]


def _clean_website(value):
    """
    Frontend templates add www. themselves.
    """
    return (
        str(value or "")
        .replace("www.", "")
        .replace("WWW.", "")
        .strip()
    )


def build_flyer(captions, input_image_path=None, output_path=None):
    """
    Prepare the complete flyer payload for the frontend.

    The actual flyer is rendered by the Next.js frontend.
    HTML-to-image handles the user's download.

    This function therefore does NOT draw the flyer with PIL.
    """

    flyer_data = _get_flyer_data(captions)

    # ─────────────────────────────────────────────────────────────
    # BASIC CONTENT
    # ─────────────────────────────────────────────────────────────

    name = _clean_string(
        flyer_data.get("name")
        or flyer_data.get("product_name"),
        "Product",
    )

    headline = _clean_string(
        flyer_data.get("headline"),
        DEFAULT_HEADLINE,
    )

    subheadline = _clean_string(
        flyer_data.get("subheadline")
        or flyer_data.get("subtext"),
    )

    cta = _clean_string(
        flyer_data.get("cta"),
        "Shop Now",
    )

    offer = _clean_string(
        flyer_data.get("offer"),
    )

    brand_name = _clean_string(
        flyer_data.get("brand_name")
        or flyer_data.get("brandName"),
    )

    # ─────────────────────────────────────────────────────────────
    # FEATURES
    # ─────────────────────────────────────────────────────────────

    features = _clean_list(
        flyer_data.get("features")
        or flyer_data.get("feature_highlights")
    )

    why_choose_us = _clean_list(
        flyer_data.get("why_choose_us")
        or flyer_data.get("whyChooseUs")
    )

    # ─────────────────────────────────────────────────────────────
    # CONTACT INFORMATION
    # ─────────────────────────────────────────────────────────────

    phone = _clean_string(
        flyer_data.get("phone")
        or flyer_data.get("phone_number")
    )

    email = _clean_string(
        flyer_data.get("email")
    )

    website = _clean_website(
        flyer_data.get("website")
    )

    address = _clean_string(
        flyer_data.get("address")
    )

    social = _clean_string(
        flyer_data.get("social")
        or flyer_data.get("social_handle")
        or flyer_data.get("instagram")
    )

    # ─────────────────────────────────────────────────────────────
    # COLORS
    # ─────────────────────────────────────────────────────────────

    colors = flyer_data.get("colors")

    if not isinstance(colors, dict):
        colors = {}

    normalized_colors = {
        "primary": colors.get(
            "primary",
            "#0a0a0a",
        ),
        "secondary": colors.get(
            "secondary",
            "#ffffff",
        ),
        "accent": colors.get(
            "accent",
            "#c9a84c",
        ),
    }

    # ─────────────────────────────────────────────────────────────
    # PRODUCT IMAGE
    # ─────────────────────────────────────────────────────────────

    product_image = _clean_string(
        flyer_data.get("product_image")
        or flyer_data.get("productImage")
        or input_image_path
    )

    # ─────────────────────────────────────────────────────────────
    # GEMINI ANALYSIS
    #
    # If flyer_generator is receiving the Gemini analysis along
    # with the generated flyer data, preserve it.
    # ─────────────────────────────────────────────────────────────

    analysis = flyer_data.get("analysis")

    if not isinstance(analysis, dict):
        analysis = {}

    visual_direction = analysis.get("visual_direction")

    if not isinstance(visual_direction, dict):
        visual_direction = {}

    # ─────────────────────────────────────────────────────────────
    # COMPLETE FRONTEND PAYLOAD
    # ─────────────────────────────────────────────────────────────

    props = {
        # Product
        "name": name,
        "productImage": product_image,

        # Brand
        "brandName": brand_name,

        # Main copy
        "headline": headline,
        "subtext": subheadline,
        "ctaText": cta,
        "extraText": offer,

        # Flyer sections
        "features": features,
        "whyChooseUs": why_choose_us,

        # Contact
        "phone": phone,
        "email": email,
        "website": website,
        "address": address,
        "social": social,

        # Design
        "colors": normalized_colors,

        # Gemini intelligence
        "analysis": analysis,
        "visualDirection": visual_direction,

        # Useful Gemini fields
        "productType": analysis.get(
            "product_type",
            "",
        ),

        "emotionalHook": analysis.get(
            "emotional_hook",
            "",
        ),

        "targetAudience": analysis.get(
            "target_audience",
            {},
        ),

        "mood": visual_direction.get(
            "mood",
            "",
        ),

        "typographyDirection": visual_direction.get(
            "typography_direction",
            "",
        ),

        "layoutEmphasis": visual_direction.get(
            "layout_emphasis",
            "",
        ),

        "lightingAndTexture": visual_direction.get(
            "lighting_and_texture",
            "",
        ),
    }

    return {
        "output_path": output_path,
        "props": props,
    }