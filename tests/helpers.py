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
