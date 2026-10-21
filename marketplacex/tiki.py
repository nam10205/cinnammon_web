"""Pure helpers for the Tiki.vn catalogue snapshot (no Flask, no network)."""
from __future__ import annotations

import html
import json
import os
import re

# (name, tiki_category_id, shop_name)
CATEGORIES: list[tuple[str, int, str]] = [
    ("Phones", 1789, "TechZone"),
    ("Computers & accessories", 8129, "TechZone"),
    ("Home appliances", 1882, "HomeNest"),
    ("Fashion", 931, "StyleHub"),
    ("Beauty", 1520, "GlowUp Beauty"),
    ("Books", 8322, "ReadMore Books"),
    ("Sports", 1975, "FitLife"),
    ("Food & drinks", 4384, "HomeNest"),
]

_TAG = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")


def clean_description(raw: str | None, limit: int = 255) -> str:
    if not raw:
        return ""
    text = html.unescape(_TAG.sub(" ", raw)).replace("\xa0", " ")
    text = _WS.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def snapshot_path() -> str:
    return os.path.join(os.path.dirname(__file__), "data", "tiki_catalog.json")


def load_snapshot() -> dict:
    with open(snapshot_path(), encoding="utf-8") as fh:
        return json.load(fh)
