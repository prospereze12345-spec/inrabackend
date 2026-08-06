import requests
from django.conf import settings


class BackgroundRemovalError(Exception):
    pass


def _try_remove_bg(image_bytes: bytes) -> bytes:
    response = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": image_bytes},
        data={"size": "auto"},
        headers={"X-Api-Key": settings.REMOVE_BG_API_KEY},
        timeout=30,
    )
    if response.status_code == 200:
        return response.content
    # 402/403 typically mean quota exhausted — signal caller to fall back
    raise BackgroundRemovalError(
        f"remove.bg failed: {response.status_code} {response.text[:200]}"
    )


def _try_pixian(image_bytes: bytes) -> bytes:
    response = requests.post(
        "https://api.pixian.ai/api/v2/remove-background",
        files={"image": image_bytes},
        auth=(settings.PIXIAN_API_ID, settings.PIXIAN_API_SECRET),
        timeout=30,
    )
    if response.status_code == 200:
        return response.content
    raise BackgroundRemovalError(
        f"pixian.ai failed: {response.status_code} {response.text[:200]}"
    )


def remove_background_from_bytes(image_bytes: bytes) -> bytes:
    try:
        return _try_remove_bg(image_bytes)
    except BackgroundRemovalError:
        # remove.bg quota hit or errored — fall back to Pixian
        return _try_pixian(image_bytes)


def remove_background(image_file):
    return remove_background_from_bytes(image_file.read())
