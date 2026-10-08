"""Extended demo catalogue built from a snapshot of https://dummyjson.com/products (data/catalog.json).

Photos are loaded online from the snapshot's CDN URLs; the SVGs in static/sample_images are only a fallback.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta

from .extensions import db
from .modules.admin import policy

USD_TO_VND = 25_000
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "catalog.json")
WIKI = "https://upload.wikimedia.org/wikipedia/commons/thumb"

# dummyjson category -> (parent, child, required attributes, shop)
CATEGORY_MAP = {
    "mens-shoes": ("Fashion", "Shoes", None, "SportZone"),
    "womens-shoes": ("Fashion", "Shoes", None, "SportZone"),
    "sports-accessories": (None, "Sports", ["color"], "SportZone"),
    "mens-shirts": ("Fashion", "Clothing", None, "StyleHouse"),
    "tops": ("Fashion", "Clothing", None, "StyleHouse"),
    "womens-dresses": ("Fashion", "Clothing", None, "StyleHouse"),
    "womens-bags": ("Fashion", "Bags", ["color"], "StyleHouse"),
    "womens-jewellery": ("Fashion", "Jewellery", ["color"], "StyleHouse"),
    "sunglasses": ("Fashion", "Sunglasses", ["color"], "StyleHouse"),
    "mens-watches": ("Fashion", "Watches", ["color"], "StyleHouse"),
    "womens-watches": ("Fashion", "Watches", ["color"], "StyleHouse"),
    "smartphones": ("Electronics", "Smartphones", ["color"], "TechHub"),
    "mobile-accessories": ("Electronics", "Accessories", None, "TechHub"),
    "laptops": ("Electronics", "Laptops", ["color"], "GadgetPro"),
    "tablets": ("Electronics", "Tablets", ["color"], "GadgetPro"),
    "furniture": ("Home & Living", "Furniture", ["color"], "HomeNest"),
    "home-decoration": ("Home & Living", "Home Decoration", ["color"], "HomeNest"),
    "kitchen-accessories": ("Home & Living", "Kitchen", ["color"], "HomeNest"),
    "groceries": (None, "Groceries", [], "FreshMart"),
    "beauty": ("Beauty", "Makeup", ["color"], "GlowBeauty"),
    "skin-care": ("Beauty", "Skin Care", ["color"], "GlowBeauty"),
    "fragrances": ("Beauty", "Fragrances", ["color"], "GlowBeauty"),
    "vehicle": ("Vehicles", "Cars", ["color"], "MotoWorld"),
    "motorcycle": ("Vehicles", "Motorcycles", ["color"], "MotoWorld"),
}

NEW_SHOPS = [
    ("GadgetPro", "gadgetpro@demo", "GadgetPro Owner", "Ho Chi Minh City"),
    ("HomeNest", "homenest@demo", "HomeNest Owner", "Hai Phong"),
    ("FreshMart", "freshmart@demo", "FreshMart Owner", "Can Tho"),
    ("GlowBeauty", "glowbeauty@demo", "GlowBeauty Owner", "Hanoi"),
    ("MotoWorld", "motoworld@demo", "MotoWorld Owner", "Hue"),
]

# Online photos for the report's 12 prototype products (closest match; titles and search data unchanged).
PROTOTYPE_PHOTOS = {
    "P01": ("dj", "Nike Air Jordan 1 Red And Black"),
    "P02": ("dj", "Sports Sneakers Off White Red"),
    "P03": ("dj", "Puma Future Rider Trainers"),
    "P04": ("url", f"{WIKI}/a/a5/Black_Converse_sneakers.JPG/500px-Black_Converse_sneakers.JPG"),
    "P05": ("dj", "Apple AirPods Max Silver"),
    "P06": ("dj", "Apple iPhone Charger"),
    "P07": ("url", f"{WIKI}/2/22/3-Tasten-Maus_Microsoft.jpg/500px-3-Tasten-Maus_Microsoft.jpg"),
    "P08": ("url", f"{WIKI}/4/42/HandKnittedWhiteLaceSock.jpg/500px-HandKnittedWhiteLaceSock.jpg"),
    "P09": ("dj", "Girl Summer Dress"),
    "P10": ("url", f"{WIKI}/9/97/Keyboard_Construction.JPG/500px-Keyboard_Construction.JPG"),
    "P11": ("dj", "Gigabyte Aorus Men Tshirt"),
    "P12": ("dj", "Vaseline Men Body and Face Lotion"),
}


def load_snapshot() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as fh:
        return json.load(fh)["products"]


def to_vnd(usd: float) -> int:
    return int(round(usd * USD_TO_VND / 1000.0)) * 1000


def prototype_photo(key: str) -> str:
    kind, value = PROTOTYPE_PHOTOS[key]
    if kind == "url":
        return value
    return next(p["thumbnail"] for p in load_snapshot() if p["title"] == value)


def _category(name: str, parent_name: str | None, schema):
    from .modules.catalog.models import Category
    parent = None
    if parent_name:
        parent = Category.query.filter_by(name=parent_name, parent_id=None).first()
        if parent is None:
            parent = Category(name=parent_name, parent_id=None, attribute_schema=["color"])
            db.session.add(parent)
            db.session.flush()
    c = Category.query.filter_by(name=name).first()
    if c is None:
        c = Category(name=name, parent_id=parent.id if parent else None,
                     attribute_schema=schema if schema is not None else ["color"])
        db.session.add(c)
        db.session.flush()
    return c


def _shops() -> dict:
    from .modules.identity import service as identity
    from .modules.identity.models import User
    from .modules.seller import service as seller
    from .modules.seller.models import Shop
    for name, email, owner_name, city in NEW_SHOPS:
        if Shop.query.filter_by(name=name).first():
            continue
        u = User(email=email, name=owner_name, role="seller", phone="0902" + str(abs(hash(name)) % 1000000).zfill(6),
                 password_hash=identity.hash_password("demo123"), created_at=policy.now() - timedelta(days=120))
        db.session.add(u)
        db.session.commit()
        s = seller.create_shop(u, name, city, f"{name} official store")
        s.verification_status = "verified"
    db.session.commit()
    return {s.name: s for s in Shop.query.all()}


def seed_bulk_catalog() -> int:
    """Add the snapshot's 194 products (skipping titles that already exist). Returns the number added."""
    from .modules.catalog import service as catalog
    from .modules.catalog.models import Product
    shops = _shops()
    existing = {t for (t,) in db.session.query(Product.title).all()}
    added = 0
    for p in load_snapshot():
        if p["title"] in existing:
            continue
        parent, child, schema, shop_name = CATEGORY_MAP[p["category"]]
        cat = _category(child, parent, schema)
        price = max(1000, to_vnd(p["price"]))
        disc = p.get("discountPercentage") or 0
        original = int(round(price / (1 - disc / 100) / 1000.0)) * 1000 if disc >= 5 else None
        attrs = {"color": "See photos"}
        if child == "Shoes":
            attrs["size"] = "40-44"
        vehicle = p["category"] in ("vehicle", "motorcycle")
        catalog.create_product(
            shops[shop_name], cat, p["title"], p.get("brand") or shop_name, p["description"], attrs,
            [{"name": "Default", "price_vnd": price, "original_price_vnd": original, "stock": int(p.get("stock") or 0),
              "purchase_limit": 1 if vehicle else 5, "sold_count": (p["id"] * 37) % 2000 + 20,
              "rating_avg": round(float(p.get("rating") or 0), 1)}],
            image_url=p["thumbnail"], status="active",
            created_at=policy.now() - timedelta(days=p["id"] % 60))
        added += 1
    return added


EXTRA_CUSTOMERS = [
    ("binh@demo", "Binh Tran", "0933111222", "45 Le Loi, District 1", "Ho Chi Minh City",
     ["Apple iPhone Charger", "Black Sun Glasses"]),
    ("chi@demo", "Chi Le", "0944222333", "8 Bach Dang", "Da Nang", ["Red Lipstick", "Basketball"]),
    ("dung@demo", "Dung Pham", "0955333444", "21 Hang Bai", "Hanoi", ["Blue Frock", "Cooking Oil"]),
]


def seed_extra_customers() -> None:
    """Three more customers with delivered orders and verified-purchase reviews (taken from the snapshot)."""
    from .modules.identity import service as identity
    from .modules.identity.models import User
    from .modules.review import service as review
    from .seed import _buy_title, _ship
    reviews = {p["title"]: p["reviews"] for p in load_snapshot()}
    for email, name, phone, line, city, titles in EXTRA_CUSTOMERS:
        u = User(email=email, name=name, role="customer", phone=phone,
                 password_hash=identity.hash_password("demo123"), created_at=policy.now() - timedelta(days=200))
        db.session.add(u)
        db.session.commit()
        identity.add_address(u, name, phone, line, city, True)
        for t in titles:
            o = _ship(_buy_title(u, t), deliver=True)
            src = (reviews.get(t) or [{"rating": 5, "comment": "Great product!"}])[0]
            review.create_review(u, o.items[0].id, int(src["rating"]), src["comment"])
