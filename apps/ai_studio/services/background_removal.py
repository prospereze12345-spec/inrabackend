from PIL import Image
import io

def remove_background(image_file):
    from rembg import remove  
    input_bytes = image_file.read()
    return remove(input_bytes)

def remove_background_from_bytes(image_bytes: bytes) -> bytes:
    from rembg import remove
    return remove(image_bytes)