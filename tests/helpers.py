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
    from marketplacex.modules.identity.models import User
    return User.query.filter_by(email=email).one()


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
