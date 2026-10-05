"""Screenshot validation: size, base64 integrity and real file type (not just the claimed one)."""
import base64
import binascii
import io

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.errors import UploadError

Image.MAX_IMAGE_PIXELS = 50_000_000          # decompression-bomb guard
ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def validate_image_b64(image_b64: str) -> tuple[bytes, str]:
    """Returns (bytes, mime_type) or raises UploadError."""
    if "," in image_b64[:100]:                # tolerate data: URLs
        image_b64 = image_b64.split(",", 1)[1]
    if len(image_b64) > settings.MAX_UPLOAD_BYTES * 4 // 3 + 16:
        raise UploadError(f"Image too large (max {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise UploadError("Image is not valid base64")
    if len(raw) > settings.MAX_UPLOAD_BYTES:
        raise UploadError(f"Image too large (max {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise UploadError("File is not a valid image")
    if fmt not in ALLOWED_FORMATS:
        raise UploadError("Unsupported image type — use PNG, JPEG or WebP")
    return raw, ALLOWED_FORMATS[fmt]
