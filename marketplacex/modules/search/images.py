"""Image encoder: a 4x4x4 RGB colour histogram, L2-normalised, serves as the feature vector (report §13).
Photo search first asks Gemini to name the product and runs that as a text search; colour is the fallback."""
from __future__ import annotations

import base64
import io
import math
import struct

from PIL import Image, ImageOps, UnidentifiedImageError

from ...errors import ValidationError

BINS = 64
FILE_ERROR = "That file is not an image. Please choose a JPG, PNG or WebP photo."


def open_image(image_bytes: bytes | None) -> Image.Image:
    """Decode an upload, upright and in RGB, or raise the error the diagrams show as "File error"."""
    if not image_bytes:
        raise ValidationError("Choose a photo to search with.")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError(FILE_ERROR)
    return img


def to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def feature_vector(image_bytes: bytes) -> list[float]:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.draft("RGB", (64, 64))   # JPEG: decode at reduced size to cap memory
        img = img.convert("RGB").resize((64, 64))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError(FILE_ERROR)
    hist = [0.0] * BINS
    for r, g, b in img.getdata():
        hist[(r // 64) * 16 + (g // 64) * 4 + (b // 64)] += 1.0
    norm = math.sqrt(sum(x * x for x in hist))
    return [x / norm for x in hist] if norm else hist


LABEL_PROMPT = ("You name products in photos for a Vietnamese online shop. Reply with only 1 to 3 search words: "
                "the brand and product line if you can recognise them (e.g. \"iPhone\", \"Samsung Galaxy\", \"Nike\"), "
                "otherwise the product type in Vietnamese as the shop's titles say it (e.g. \"nồi chiên\", \"tai nghe\", "
                "\"bàn phím\"). No model numbers, colours or sizes. Shop categories: {categories}. "
                "If there is no product, reply with nothing.")


def describe(image_bytes: bytes, categories: list[str]) -> str | None:
    """Ask Gemini what the photo shows, as a text query. None when Gemini is unavailable or unsure."""
    from ..assistant.service import AssistantUnavailable, _call_gemini
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((512, 512))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    try:
        text = _call_gemini(LABEL_PROMPT.format(categories=", ".join(categories)), [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}]}], timeout=45)
    except AssistantUnavailable:
        return None
    text = text.strip().strip('"“”').strip()
    return text[:120] or None


def pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack(b: bytes | None) -> list[float] | None:
    if not b:
        return None
    return list(struct.unpack(f"<{len(b) // 4}f", b))


def solid_image(rgb: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), rgb).save(buf, format="PNG")
    return buf.getvalue()
