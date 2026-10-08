"""Simulated image encoder: sample photos map to the prototype's 3-dimension vectors (report §13)."""
from __future__ import annotations

SAMPLE_IMAGES: dict[str, tuple] = {
    "black-sneaker": (0.93, 0.09, 0.11),
    "wireless-mouse": (0.10, 0.95, 0.05),
    "summer-dress": (0.20, 0.10, 0.95),
}
