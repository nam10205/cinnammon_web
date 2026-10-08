"""Demo seed data. Uses services so invariants hold."""
from __future__ import annotations

from datetime import timedelta

from .extensions import db
from .modules.admin import policy
from .modules.admin.policy import ensure_defaults

DEMO_PASSWORD = "demo123"

USERS = [
    ("alice@demo", "Alice Nguyen", "customer", "0912345678"),
    ("sportzone@demo", "SportZone Owner", "seller", "0901000001"),
    ("techhub@demo", "TechHub Owner", "seller", "0901000002"),
    ("stylehouse@demo", "StyleHouse Owner", "seller", "0901000003"),
    ("admin@demo", "Platform Admin", "admin", "0900000000"),
    ("support@demo", "Support Agent", "support", "0900000001"),
    ("risk@demo", "Risk Analyst", "risk", "0900000002"),
]

SHOPS = [("SportZone", "sportzone@demo", "Hanoi"), ("TechHub", "techhub@demo", "Ho Chi Minh City"),
         ("StyleHouse", "stylehouse@demo", "Da Nang")]

# key: (title, brand, shop, category, price, original, rating, sold, vector, color, description)
PRODUCTS = {
    "P01": ("Nike Air Zoom Black Running Shoes", "Nike", "SportZone", "Shoes", 1990000, 2490000, 4.9, 1200, (0.80, 0.30, 0.20), "black",
            "Lightweight Nike running shoes in black with responsive cushioning (giày chạy bộ màu đen)."),
    "P02": ("Adidas Ultraboost White Running Shoes", "Adidas", "SportZone", "Shoes", 2350000, None, 4.8, 900, (0.85, 0.25, 0.15), "white",
            "Adidas Ultraboost running shoes in white with boost midsole."),
    "P03": ("Biti's Hunter Black Sneakers", "Biti's", "SportZone", "Shoes", 899000, 1050000, 4.7, 3000, (0.93, 0.09, 0.11), "black",
            "Vietnamese Biti's Hunter sneakers in black for everyday wear (giày sneaker màu đen)."),
    "P04": ("Converse Classic Canvas Shoes", "Converse", "SportZone", "Shoes", 1450000, None, 4.6, 500, (0.75, 0.20, 0.40), "white",
            "Converse classic canvas shoes, a timeless low-top."),
    "P05": ("Sony Wireless Noise Cancelling Headphones", "Sony", "TechHub", "Accessories", 6490000, 7490000, 4.8, 300, (0.10, 0.90, 0.20), "black",
            "Sony wireless noise cancelling headphones with 30-hour battery."),
    "P06": ("Anker 65W USB-C Charger", "Anker", "TechHub", "Accessories", 590000, None, 4.7, 800, (0.05, 0.85, 0.10), "white",
            "Compact Anker 65W USB-C charger for laptops and phones."),
    "P07": ("Logitech Wireless Mouse", "Logitech", "TechHub", "Accessories", 429000, 499000, 4.8, 2500, (0.10, 0.95, 0.05), "black",
            "Logitech wireless mouse with silent clicks and long battery life."),
    "P08": ("Puma Black Sport Socks", "Puma", "SportZone", "Clothing", 99000, None, 4.5, 4000, (0.60, 0.10, 0.70), "black",
            "Puma black sport socks, pack of three."),
    "P09": ("Women Linen Summer Dress", "StyleHouse", "StyleHouse", "Clothing", 349000, 450000, 4.6, 700, (0.20, 0.10, 0.95), "beige",
            "Breathable women linen summer dress."),
    "P10": ("RGB Mechanical Keyboard", "Keychron", "TechHub", "Accessories", 1190000, None, 4.7, 600, (0.10, 0.88, 0.30), "black",
            "RGB mechanical keyboard with hot-swappable switches."),
    "P11": ("Men Cotton T Shirt Black", "StyleHouse", "StyleHouse", "Clothing", 129000, None, 4.6, 5000, (0.25, 0.05, 0.90), "black",
            "Men cotton t shirt in black, regular fit."),
    "P12": ("Skincare Sunscreen SPF50", "StyleHouse", "StyleHouse", "Beauty", 489000, None, 4.9, 1500, (0.15, 0.30, 0.85), "white",
            "Skincare sunscreen SPF50 for daily protection."),
}
SEED_KEYS = {k: v[0] for k, v in PRODUCTS.items()}


def seed_catalog() -> None:
    from .modules.catalog import service as catalog
    from .modules.catalog.models import Category
    from .modules.identity import service as identity
    from .modules.identity.models import User
    from .modules.seller import service as seller

    ensure_defaults()
    users = {}
    for email, name, role, phone in USERS:
        u = User(email=email, name=name, role=role, phone=phone, password_hash=identity.hash_password(DEMO_PASSWORD),
                 created_at=policy.now() - timedelta(days=90))
        db.session.add(u)
        users[email] = u
    db.session.commit()
    identity.add_address(users["alice@demo"], "Alice Nguyen", "0912345678", "12 Trang Tien, Hoan Kiem", "Hanoi", True)

    shops = {}
    for name, owner, loc in SHOPS:
        s = seller.create_shop(users[owner], name, loc, f"{name} official store")
        s.verification_status = "verified"
        shops[name] = s
    db.session.commit()

    def add_cat(name, parent=None, schema=None):
        c = Category(name=name, parent_id=parent.id if parent else None, attribute_schema=schema or ["color"])
        db.session.add(c)
        db.session.flush()
        return c
    fashion = add_cat("Fashion")
    electronics = add_cat("Electronics")
    cats = {"Shoes": add_cat("Shoes", fashion, ["size", "color"]), "Clothing": add_cat("Clothing", fashion),
            "Accessories": add_cat("Accessories", electronics), "Beauty": add_cat("Beauty")}
    db.session.commit()

    for key, (title, brand, shop, cat, price, orig, rating, sold, vec, color, desc) in PRODUCTS.items():
        attrs = {"color": color}
        if cat == "Shoes":
            attrs["size"] = "42"
        age = 60 if key in ("P04", "P10") else 10
        catalog.create_product(
            shops[shop], cats[cat], title, brand, desc, attrs,
            [{"name": "Default", "price_vnd": price, "original_price_vnd": orig, "stock": 50, "purchase_limit": 5,
              "sold_count": sold, "rating_avg": rating}],
            image_url=f"/static/sample_images/{key}.svg", image_vector=vec, status="active",
            created_at=policy.now() - timedelta(days=age))


def seed_promotions() -> None:
    from .modules.promotion.models import Campaign, Voucher
    from .modules.seller.models import Shop
    now = policy.now()
    c = Campaign(name="10.10 Sale", budget_vnd=10_000_000, starts_at=now - timedelta(days=1),
                 ends_at=now + timedelta(days=30), active=True)
    db.session.add(c)
    db.session.flush()
    sz = Shop.query.filter_by(name="SportZone").one()
    db.session.add_all([
        Voucher(campaign_id=c.id, code="SALE10", kind="percent", value=10, max_discount_vnd=100_000,
                min_spend_vnd=0, usage_limit=1000),
        Voucher(campaign_id=c.id, code="SPORT80", kind="fixed", value=80_000, min_spend_vnd=500_000,
                shop_id=sz.id, usage_limit=500),
    ])
    db.session.commit()


def _buy(customer, key: str, qty: int = 1, codes=None):
    """Place and pay an order through the real checkout saga."""
    import uuid

    from .modules.cart import service as cart
    from .modules.catalog.models import Product
    from .modules.checkout import service as checkout
    from .modules.order import service as order_service
    from .modules.payment import service as payment
    p = Product.query.filter_by(title=SEED_KEYS[key]).one()
    cart.add_item(customer, p.variants[0].offer.id, qty)
    g = checkout.quote(customer, customer.addresses[0].id, codes or [])
    checkout.place_order(customer, g.id, uuid.uuid4().hex, g.quote_hash)
    pa = payment.latest_for_group(g.id)
    body = payment.simulate(pa.id, "success")
    payment.handle_callback(body["payload"], body["signature"])
    return order_service.orders_of_group(g.id)[0]


def _ship(order, deliver: bool):
    from .modules.identity.models import User
    from .modules.logistics import service as logistics
    from .modules.seller import service as seller
    owner = db.session.get(User, order.shop.owner_id)
    seller.accept(owner, order.id)
    sh = seller.pack(owner, order.id, 700)
    seller.hand_over(owner, order.id)
    while deliver and order.status != "Delivered":
        logistics.advance(sh)
    return order


def seed_demo_orders() -> None:
    from .modules.identity.models import User
    from .modules.returns import service as returns
    from .modules.settlement import service as settlement
    alice = User.query.filter_by(email="alice@demo").one()
    admin = User.query.filter_by(email="admin@demo").one()
    _ship(_buy(alice, "P11", 2), deliver=True)
    policy.advance_clock(8 * 24)  # demo clock: let the first order's return window close
    settlement.release_eligible(admin)
    o = _ship(_buy(alice, "P01", 1), deliver=True)
    returns.open_case(alice, o.id, {o.items[0].id: 1}, "Size does not fit", "return_and_refund",
                      "Size 42 is too small, I would like to return it.")
    _ship(_buy(alice, "P07", 1), deliver=False)
    _buy(alice, "P12", 1)
    _ship(_buy(alice, "P03", 1), deliver=True)


def seed_listings() -> None:
    """A listing waiting in the moderation queue (contains a prohibited term)."""
    from .modules.catalog import service as catalog
    from .modules.catalog.models import Category
    from .modules.seller.models import Shop
    catalog.create_product(Shop.query.filter_by(name="SportZone").one(), Category.query.filter_by(name="Shoes").one(),
                           "Replica Running Shoes", "NoBrand", "Looks just like the famous brand.",
                           {"size": "42", "color": "red"},
                           [{"name": "Default", "price_vnd": 350000, "stock": 20, "purchase_limit": 5}],
                           image_url="/static/sample_images/placeholder.svg", status="pending")


def seed_risk() -> None:
    """A high-value checkout held for risk review."""
    import uuid

    from .modules.cart import service as cart
    from .modules.catalog.models import Product
    from .modules.checkout import service as checkout
    from .modules.identity.models import User
    alice = User.query.filter_by(email="alice@demo").one()
    p = Product.query.filter_by(title=SEED_KEYS["P05"]).one()
    cart.add_item(alice, p.variants[0].offer.id, 4)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, uuid.uuid4().hex, g.quote_hash)


def seed_all_for_tests() -> None:
    """Catalogue + promotions, without demo orders (tests build their own)."""
    seed_catalog()
    for fn in ("seed_promotions", "seed_listings"):
        f = globals().get(fn)
        if f:
            f()


def run() -> None:
    seed_catalog()
    for fn in ("seed_promotions", "seed_listings", "seed_demo_orders", "seed_risk", "seed_chat"):
        f = globals().get(fn)
        if f:
            f()
