from rembg import remove
from PIL import Image
import io

def remove_background(image_file):
    """Original — accepts Django UploadedFile"""
    input_bytes = image_file.read()
    return remove(input_bytes)

def remove_background_from_bytes(image_bytes: bytes) -> bytes:
    """For use inside Celery tasks where you already have raw bytes"""
    return remove(image_bytes)