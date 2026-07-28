def build_product_context(llava_response):

    return {
        "product": llava_response,
        "audience": "general",
        "selling_angle": "value + urgency",
        "style": "modern sales copy"
    }
