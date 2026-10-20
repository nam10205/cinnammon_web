"""Lookup and journey helpers shared by tests (see plan: Test Helpers)."""
from marketplacex.extensions import db
from marketplacex.seed import SEED_KEYS


def _product(key):
    from marketplacex.modules.catalog.models import Product
    return Product.query.filter_by(title=SEED_KEYS[key]).one()


def product_id(key):
    return _product(key).id


def offer_id(key):
    return _product(key).variants[0].offer.id


def shop_id(name):
    from marketplacex.modules.seller.models import Shop
    return Shop.query.filter_by(name=name).one().id


def user_by_email(email):
    from marketplacex.modules.identity.models import Account
    return Account.query.filter_by(email=email).one()


def user_id(email):
    return user_by_email(email).id


def seller_user(email):
    return user_by_email(email)


def alice_user():
    return user_by_email("alice@demo")


def cat(name):
    from marketplacex.modules.catalog.models import Category
    return Category.query.filter_by(name=name).one()


def captured_payment(amount, group_id=1, attempt="att-cap"):
    from marketplacex.modules.payment import service as pay
    p = pay.authorize(group_id, amount, attempt)
    body = pay.simulate(p.id, "success")
    pay.handle_callback(body["payload"], body["signature"])
    return p


def _callback(group_id, outcome):
    from marketplacex.modules.payment import service as pay
    p = pay.latest_for_group(group_id)
    body = pay.simulate(p.id, outcome)
    pay.handle_callback(body["payload"], body["signature"])
    return p


def pay_success(group_id):
    return _callback(group_id, "success")


def pay_fail(group_id):
    return _callback(group_id, "fail")


def paid_order(customer, key, qty=1):
    import uuid
    from marketplacex.modules.cart import service as cart
    from marketplacex.modules.checkout import service as checkout
    from marketplacex.modules.order import service as order_service
    cart.add_item(customer, offer_id(key), qty)
    g = checkout.quote(customer, customer.addresses[0].id, [])
    checkout.place_order(customer, g.id, uuid.uuid4().hex, g.quote_hash)
    pay_success(g.id)
    return order_service.orders_of_group(g.id)[0]


def _owner_of(order):
    from marketplacex.modules.identity.models import Account
    return db.session.get(Account, order.shop.owner_id)


def shipped_order(customer, key, qty=1):
    from marketplacex.modules.seller import service as seller
    o = paid_order(customer, key, qty)
    s = _owner_of(o)
    seller.accept(s, o.id)
    seller.pack(s, o.id, 800)
    seller.hand_over(s, o.id)
    return o


def delivered_order(customer, key, qty=1):
    from marketplacex.modules.logistics import service as logistics
    o = shipped_order(customer, key, qty)
    sh = o.shipments[0]
    while o.status != "Delivered":
        logistics.advance(sh)
    return o


def c_return_shipment(case):
    from marketplacex.modules.logistics.models import Shipment
    return Shipment.query.filter_by(return_case_id=case.id, kind="return").one()


def disputed_case(customer, key="P03"):
    from marketplacex.modules.returns import service as returns
    o = delivered_order(customer, key)
    c = returns.open_case(customer, o.id, {o.items[0].id: 1}, "not as described", "refund_only", "looks fake")
    returns.seller_respond(_owner_of(o), c.id, "reject", "item is genuine")
    returns.escalate(customer, c.id, "photos attached")
    return c


def valid_listing_data():
    return {"category_id": cat("Shoes").id, "title": "Trail Runner Pro", "brand": "SportZone",
            "description": "Grippy trail running shoes", "attributes": {"size": "41", "color": "green"},
            "variants": [{"name": "Size 41", "price_vnd": 1200000, "original_price_vnd": None, "stock": 10,
                          "purchase_limit": 3},
                         {"name": "Size 42", "price_vnd": 1250000, "original_price_vnd": 1400000, "stock": 5,
                          "purchase_limit": 3}]}


def pending_product():
    from marketplacex.modules.catalog.models import Product
    return Product.query.filter_by(status="pending").first()
