"""Production seed: the Tiki.vn catalogue snapshot (data/tiki_catalog.json) plus demo accounts and orders.

Run by `flask --app marketplacex.app init-db`. Products are inserted in one flush and one commit per
category, so seeding a remote Postgres (Supabase) takes a few round trips per table, not per row.
"""
from __future__ import annotations

import base64
import random
import re
from datetime import timedelta

from . import seed, tiki
from .extensions import db
from .modules.admin import policy
from .modules.admin.models import Clock

PASSWORD = seed.DEMO_PASSWORD
UNBRANDED = "Unbranded"

ADMIN = ("admin@demo", "Platform Admin", "0900000000")

SHOP_CITIES = {
    "TechZone": "Ho Chi Minh City", "HomeNest": "Hanoi", "StyleHub": "Ho Chi Minh City",
    "GlowUp Beauty": "Hanoi", "ReadMore Books": "Hanoi", "FitLife": "Ho Chi Minh City",
}

# (email, name in First Middle Last order, phone, (street, ward, district, city)); alice is first so the
# one-click *customer* demo login picks her.
CUSTOMERS = [
    ("alice@demo", "Alice Nguyen", "0912345678", ("12 Trang Tien", "Trang Tien", "Hoan Kiem", "Hanoi")),
    ("binh@demo", "Binh Van Tran", "0933111222", ("45 Le Loi", "Ben Nghe", "District 1", "Ho Chi Minh City")),
    ("chi@demo", "Chi Thi Le", "0944222333", ("21 Hang Bai", "Hang Bai", "Hoan Kiem", "Hanoi")),
    ("dung@demo", "Dung Quoc Pham", "0955333444", ("120 Nguyen Trai", "Ben Thanh", "District 1", "Ho Chi Minh City")),
    ("giang@demo", "Giang Thu Hoang", "0966444555", ("25 Kim Ma", "Kim Ma", "Ba Dinh", "Hanoi")),
    ("hoa@demo", "Hoa Minh Vu", "0977555666", ("18 Vo Van Tan", "Vo Thi Sau", "District 3", "Ho Chi Minh City")),
    ("khanh@demo", "Khanh Duc Dang", "0988666777", ("102 Tran Duy Hung", "Trung Hoa", "Cau Giay", "Hanoi")),
    ("linh@demo", "Linh Ngoc Bui", "0399777888", ("56 Phan Xich Long", "Ward 2", "Phu Nhuan", "Ho Chi Minh City")),
    ("minh@demo", "Minh Anh Do", "0388888999", ("9 Thai Ha", "Trung Liet", "Dong Da", "Hanoi")),
    ("nam@demo", "Nam Hoang Ngo", "0377999000", ("210 Nguyen Thi Thap", "Tan Phu", "District 7", "Ho Chi Minh City")),
]

ORDERS_PER_CUSTOMER = 2
REVIEW_COMMENTS = {
    5: ["Excellent quality, exactly as described. Fast delivery!", "Very happy with this purchase, highly recommend.",
        "Great value for the price. Would buy again."],
    4: ["Good product, packaging could be better.", "Works well, delivery took a little longer than expected.",
        "Nice quality overall, matches the photos."],
}
CHAT_TECHZONE = ("Hi! Does this phone come with an official Vietnam warranty?",
                 "Hello Alice, yes: every phone we sell has a 12-month official warranty in Vietnam.")


def shop_email(shop_name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", shop_name.lower()) + "@demo"


def _shops(snapshot: dict) -> list[str]:
    names = [shop for _, _, shop in tiki.CATEGORIES] + [c["shop"] for c in snapshot["categories"]]
    return list(dict.fromkeys(names))


def _accounts(shop_names: list[str]) -> tuple[dict, list]:
    from .modules.identity import service as identity
    from .modules.seller import service as seller
    from .modules.seller.models import Shop
    joined = policy.now() - timedelta(days=180)
    identity.create_account(ADMIN[0], ADMIN[1], "admin", PASSWORD, phone=ADMIN[2], created_at=joined)
    for i, name in enumerate(shop_names):
        owner = identity.create_account(shop_email(name), f"{name} Owner", "seller", PASSWORD,
                                        phone=f"09010000{i + 1:02d}", created_at=joined)
        s = seller.create_shop(owner, name, SHOP_CITIES.get(name, "Hanoi"), f"{name} official store on MarketplaceX")
        s.verification_status = "verified"
    db.session.commit()
    shops = {s.name: s for s in Shop.query.all()}
    customers = []
    for i, (email, name, phone, (street, ward, district, city)) in enumerate(CUSTOMERS):
        u = identity.create_account(email, name, "customer", PASSWORD, phone=phone,
                                    created_at=joined + timedelta(days=i * 7))
        identity.add_address(u, u.name, phone, street, ward, district, city, is_default=True)
        customers.append(u)
    return shops, customers


def _variants(p: dict) -> list[dict]:
    """One variant per Tiki option (or "Default"); sold and review counts split across them."""
    names = list(dict.fromkeys(o.strip()[:80] for o in p.get("options") or [] if o and o.strip())) or ["Default"]
    rng = random.Random(p["tiki_id"])
    n = len(names)
    sold, reviews = int(p.get("sold") or 0), int(p.get("review_count") or 0)
    price, listed = int(p["price"]), int(p.get("list_price") or 0)
    return [{"name": name, "price_vnd": price, "original_price_vnd": listed if listed > price else None,
             "stock": rng.randint(20, 200), "purchase_limit": 5,
             "sold_count": sold // n + (sold % n if i == 0 else 0),
             "rating_avg": float(p.get("rating") or 0.0),
             "rating_count": reviews // n + (reviews % n if i == 0 else 0)}
            for i, name in enumerate(names)]


def _vectors(p: dict) -> list[bytes | None]:
    return [base64.b64decode(v) if v else None for v in p.get("vectors") or []]


def _catalogue(snapshot: dict, shops: dict) -> tuple[int, int]:
    from .modules.catalog import service as catalog
    from .modules.catalog.models import Category
    categories = products = 0
    now = policy.now()
    for cat in snapshot["categories"]:
        c = Category(name=cat["name"], description=f"{cat['name']} from Tiki.vn", parent_id=None,
                     attribute_schema=[])
        db.session.add(c)
        db.session.flush()
        shop = shops[cat["shop"]]
        for i, p in enumerate(cat["products"]):
            catalog.create_product(
                shop, c, p["name"].strip(), (p.get("brand") or "").strip() or UNBRANDED,
                tiki.clean_description(p.get("description")), {}, _variants(p),
                image_urls=p.get("images") or [], vectors=_vectors(p), status="active",
                created_at=now - timedelta(days=i % 60), commit=False)
            products += 1
        db.session.commit()
        categories += 1
    return categories, products


def _orders(customers: list) -> tuple[int, int]:
    """Two delivered orders per customer on deterministic products, each with a 4- or 5-star review."""
    from .modules.catalog.models import Offer, Variant
    from .modules.review import service as review
    first_offer = {}   # product id -> its first variant's offer
    for oid, pid in db.session.query(Offer.id, Variant.product_id).join(Variant).order_by(Variant.id).all():
        first_offer.setdefault(pid, oid)
    picks = [first_offer[pid] for pid in sorted(first_offer)]
    if not picks:
        return 0, 0
    orders = reviews = 0
    for ci, customer in enumerate(customers):
        for k in range(ORDERS_PER_CUSTOMER):
            offer_id = picks[(ci * 7 + k * 31 + 3) % len(picks)]
            o = seed._ship(seed._buy_offer(customer, offer_id), deliver=True)
            orders += 1
            rating = 5 if (ci + k) % 3 else 4
            comment = REVIEW_COMMENTS[rating][(ci + k) % len(REVIEW_COMMENTS[rating])]
            review.create_review(customer, o.items[0].id, rating, comment)
            reviews += 1
    return orders, reviews


def run(snapshot: dict | None = None) -> dict:
    """Seed a fresh database (tables already created) and return the row counts."""
    snapshot = snapshot or tiki.load_snapshot()
    session = db.session()
    # Services commit after every step; reloading every expired row afterwards costs a round trip each on a
    # remote database. The seed is the only writer and issues no bulk SQL updates, so in-memory state stays
    # current without the reloads.
    expire_on_commit, session.expire_on_commit = session.expire_on_commit, False
    try:
        policy.now()
        clock = db.session.get(Clock, 1)  # noqa: F841  held so the identity map (weak references) keeps it cached
        shops, customers = _accounts(_shops(snapshot))
        categories, products = _catalogue(snapshot, shops)
        first_shop = tiki.CATEGORIES[0][2]
        seed.seed_promotions(shop_name=first_shop, shop_code="TECH80")
        orders, reviews = _orders(customers)
        seed.seed_chat(shop_name=first_shop, messages=CHAT_TECHZONE)
    finally:
        session.expire_on_commit = expire_on_commit
    return {"categories": categories, "products": products, "customers": len(customers),
            "orders": orders, "reviews": reviews}
