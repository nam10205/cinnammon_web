"""Fetch a Tiki.vn catalogue snapshot into marketplacex/data/tiki_catalog.json.

Run: .venv/bin/python -I scripts/fetch_tiki.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from marketplacex import tiki  # noqa: E402

try:
    from marketplacex.modules.search.images import feature_vector, pack  # noqa: E402
except Exception:  # pragma: no cover
    feature_vector = pack = None

TARGET = 65
LISTING = "https://tiki.vn/api/personalish/v1/blocks/listings?limit=40&category={cat}&page={page}"
DETAIL = "https://tiki.vn/api/v2/products/{id}"
UA = {"User-Agent": "Mozilla/5.0"}


def get(url: str) -> bytes:
    last: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            time.sleep(0.3)
            return data
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def get_json(url: str):
    return json.loads(get(url).decode("utf-8"))


def medium(url: str) -> str:
    """Prefer a 750x750 cached variant of the original Tiki CDN image."""
    marker = "/ts/"
    if "/cache/" not in url and marker in url:
        head, tail = url.split(marker, 1)
        return f"{head}/cache/750x750/ts/{tail}"
    return url


def build_product(item: dict) -> dict | None:
    pid = item["id"]
    price = item.get("price") or 0
    if price <= 0:
        return None
    d = get_json(DETAIL.format(id=pid))
    bases = [i["base_url"] for i in (d.get("images") or []) if i.get("base_url")][:3]
    images = [medium(u) for u in bases]
    images = [u for u in images if len(u) <= 500]
    if not images:
        return None
    options: list[str] = []
    for opt in d.get("configurable_options") or []:
        for v in opt.get("values") or []:
            if v.get("label") and len(options) < 3:
                options.append(str(v["label"])[:255])
    vec = None
    raw = None
    for cand in (images[0], bases[0]):
        try:
            raw = get(cand)
            images[0] = cand
            break
        except Exception as exc:  # noqa: BLE001
            print(f"   image failed for {pid}: {exc}")
    if raw is None:
        return None
    if feature_vector:
        try:
            vec = base64.b64encode(pack(feature_vector(raw))).decode("ascii")
        except Exception as exc:  # noqa: BLE001
            print(f"   vector failed for {pid}: {exc}")
    brand = item.get("brand_name") or (d.get("brand") or {}).get("name") or ""
    return {
        "tiki_id": pid,
        "name": (d.get("name") or item.get("name") or "")[:255],
        "brand": brand[:255],
        "description": tiki.clean_description(d.get("description") or d.get("short_description")),
        "price": int(price),
        "list_price": int(item.get("list_price") or price),
        "rating": float(item.get("rating_average") or 0),
        "review_count": int(item.get("review_count") or 0),
        "sold": int((item.get("quantity_sold") or {}).get("value") or 0),
        "images": images,
        "options": options,
        "vectors": [vec] + [None] * (len(images) - 1),
    }


def fetch_category(name: str, cat: int, seen: set[int]) -> list[dict]:
    products: list[dict] = []
    page = 1
    while len(products) < TARGET:
        try:
            listing = get_json(LISTING.format(cat=cat, page=page))
        except Exception as exc:  # noqa: BLE001
            print(f"  listing page {page} failed: {exc}")
            break
        items = listing.get("data") or []
        if not items:
            break
        for item in items:
            if len(products) >= TARGET:
                break
            if item["id"] in seen:
                continue
            try:
                p = build_product(item)
            except Exception as exc:  # noqa: BLE001
                print(f"  skip {item['id']}: {exc}")
                continue
            if p:
                seen.add(item["id"])
                products.append(p)
        last = (listing.get("paging") or {}).get("last_page", page)
        if page >= last:
            break
        page += 1
    return products


def main() -> None:
    seen: set[int] = set()
    cats = []
    for name, cat, shop in tiki.CATEGORIES:
        products = fetch_category(name, cat, seen)
        print(f"{name} (category {cat}): {len(products)} products", flush=True)
        if len(products) < TARGET:
            print(f"  WARNING: {name} has fewer than {TARGET}; choose another category id")
        cats.append({"name": name, "shop": shop, "products": products})
    out = {
        "source": "https://tiki.vn",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "categories": cats,
    }
    with open(tiki.snapshot_path(), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("wrote", tiki.snapshot_path())


if __name__ == "__main__":
    main()
