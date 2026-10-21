"""Seed the 8 ERD tables from the Tiki.vn snapshot (data/tiki_catalog.json) plus demo customers.

Run by `flask --app marketplacex.app init-db`. Rows go in with add_all and one commit per category, so seeding
a remote Postgres (Supabase) costs a few round trips per category, not one per row.
"""
from __future__ import annotations

import base64
import random
from datetime import timedelta

from . import clock, tiki
from .extensions import db
from .modules.catalog.models import Category, Product, ProductImage
from .modules.identity.models import Address, Customer, FullName
from .modules.order.models import Order
from .modules.order.service import shipping_fee
from .modules.search.models import SearchHistory

UNBRANDED = "Unbranded"

# (email, "First Middle Last", phone, (street, ward, district, city)); alice is first so the one-click
# customer demo login picks her.
_RAW_CUSTOMERS = [
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


def _customer_fields(email, name, phone, addr):
    parts = name.split()
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    number, _, street = addr[0].partition(" ")
    return {"email": email, "phone": phone, "first": parts[0], "middle": middle, "last": parts[-1],
            "ward": addr[1], "street": street, "detail": f"{number}, {addr[2]}, {addr[3]}"}


CUSTOMERS = [_customer_fields(*c) for c in _RAW_CUSTOMERS]

_KEYWORDS = ["iphone", "áo thun", "tai nghe bluetooth", "son môi", "sách kỹ năng", "giày chạy bộ",
             "nồi chiên không dầu", "cà phê", "bàn phím cơ", "kem chống nắng"]
_TYPES = ["text", "voice", "image"]


def _build_searches():
    rows, text_voice = [], 0
    for i in range(30):
        kind = _TYPES[i % 3]
        if kind == "image":
            keyword = "photo.jpg"
        else:
            keyword = _KEYWORDS[text_voice % len(_KEYWORDS)]
            text_voice += 1
        rows.append((i // 3, keyword, kind))   # (customer index, keyword, searchType)
    return rows


SEARCHES = _build_searches()


def run(snapshot: dict | None = None) -> dict:
    """Seed freshly created tables and return row counts keyed by table name."""
    snapshot = snapshot or tiki.load_snapshot()
    now = clock.now()
    session = db.session
    n_products = n_images = 0
    for cat in snapshot["categories"]:
        category = Category(name=cat["name"], description=f"{cat['name']} from Tiki.vn")
        session.add(category)
        for i, p in enumerate(cat["products"]):
            stamp = now - timedelta(days=i % 60)
            product = Product(
                category=category, title=(p.get("name") or "").strip()[:255],
                brand=((p.get("brand") or "").strip() or UNBRANDED)[:255],
                description=tiki.clean_description(p.get("description")),
                price=int(p["price"]), stock_quantity=random.Random(p["tiki_id"]).randint(20, 200),
                avg_rating=float(p.get("rating") or 0), created_at=stamp, updated_at=stamp)
            vectors = p.get("vectors") or []
            for k, url in enumerate((p.get("images") or [])[:3]):
                vec = vectors[k] if k < len(vectors) else None
                product.images.append(ProductImage(
                    url=url, feature_vector=base64.b64decode(vec) if vec else None))
                n_images += 1
            session.add(product)
            n_products += 1
        session.commit()

    customers = []
    for c in CUSTOMERS:
        customers.append(Customer(
            email=c["email"], phone_number=c["phone"],
            full_name=FullName(first_name=c["first"], middle_name=c["middle"], last_name=c["last"]),
            address=Address(ward=c["ward"], street=c["street"], detail=c["detail"])))
    session.add_all(customers)
    session.flush()
    session.add_all(SearchHistory(customer_id=customers[ci].id, keyword=kw, search_type=kind,
                                  searched_at=now - timedelta(hours=i + 1))
                    for i, (ci, kw, kind) in enumerate(SEARCHES))
    session.commit()

    products = Product.query.order_by(Product.id).all()
    total = len(products)
    orders = []
    for ci, customer in enumerate(customers):
        for k in (0, 1):
            product = products[(ci * 7 + k * 31 + 3) % total]
            qty = 1 + (ci + k) % 2
            card = (ci + k) % 2 == 0
            ordered = now - timedelta(days=ci * 3 + k + 1)
            fee = shipping_fee(qty * product.price)
            order = Order(customer_id=customer.id, product_id=product.id, address_id=customer.address_id,
                          quantity=qty, unit_price=product.price, shipping_fee=fee,
                          total_price=qty * product.price + fee,
                          payment_method="card" if card else "cod", ordered_at=ordered)
            if (ci, k) in ((3, 1), (7, 1)):
                order.status = "cancelled"
                order.payment_status = "refunded" if card else "unpaid"
            else:
                order.status = "delivered"
                order.payment_status = "paid"
                order.shipped_at = ordered + timedelta(seconds=40)
                order.delivered_at = order.shipped_at + timedelta(seconds=20)
            orders.append(order)
    session.add_all(orders)
    session.commit()

    return {"FullName": len(customers), "Address": len(customers), "Customer": len(customers),
            "SearchHistory": 30, "Category": len(snapshot["categories"]), "Product": n_products,
            "ProductImage": n_images, "Order": len(orders)}
