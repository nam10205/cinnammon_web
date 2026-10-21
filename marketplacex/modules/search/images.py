"""Image encoder: a 4x4x4 RGB colour histogram, L2-normalised, serves as the feature vector (report §13)."""
from __future__ import annotations

import io
import math
import struct

from PIL import Image, UnidentifiedImageError

from ...errors import ValidationError

BINS = 64


def feature_vector(image_bytes: bytes) -> list[float]:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB").resize((64, 64))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError("That file is not an image")
    hist = [0.0] * BINS
    for r, g, b in img.getdata():
        hist[(r // 64) * 16 + (g // 64) * 4 + (b // 64)] += 1.0
    norm = math.sqrt(sum(x * x for x in hist))
    return [x / norm for x in hist] if norm else hist


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
