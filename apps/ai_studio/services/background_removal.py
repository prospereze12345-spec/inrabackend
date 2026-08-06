from rembg import new_session, remove


_session = new_session("u2net")


def remove_background(image_file):
    input_bytes = image_file.read()
    return remove(input_bytes, session=_session)


def remove_background_from_bytes(image_bytes: bytes) -> bytes:
    return remove(image_bytes, session=_session)
