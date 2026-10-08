import itertools

import pytest

from marketplacex.app import create_app
from marketplacex.extensions import db

_seq = itertools.count(1)


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SECRET_KEY": "t",
        "PAYMENT_WEBHOOK_SECRET": "whsec",
        "NOTIFICATION_FAILURE_RATE": 0,
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "GEMINI_API_KEY": "",
    })
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    from marketplacex.modules.admin import policy
    policy.ensure_defaults()
    yield app
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    from marketplacex.modules.identity.models import User
    from marketplacex.modules.identity.service import hash_password

    def _make(role="customer", email=None):
        n = next(_seq)
        u = User(email=email or f"{role}{n}@test", name=f"{role.title()} {n}",
                 role=role, password_hash=hash_password("pw12345"))
        db.session.add(u)
        db.session.commit()
        return u
    return _make


@pytest.fixture
def login():
    def _login(client, user):
        with client.session_transaction() as s:
            s["user_id"] = user.id
    return _login


@pytest.fixture
def seeded(app):
    from marketplacex import seed
    seed.seed_all_for_tests()
    return True


@pytest.fixture
def alice(seeded):
    from helpers import alice_user
    return alice_user()


@pytest.fixture
def make_order(seeded):
    from helpers import alice_user, offer_id
    from marketplacex.modules.admin import policy
    from marketplacex.modules.catalog import service as catalog
    from marketplacex.modules.order.models import Order, OrderItem

    def _make(status="Draft", key="P03", qty=1):
        o = catalog.get_offer(offer_id(key))
        a = alice_user()
        order = Order(group_id=0, attempt_id="test", shop_id=o.shop_id, customer_id=a.id, status=status,
                      address_snapshot=a.addresses[0].as_dict(), merchandise_vnd=o.price_vnd * qty,
                      discount_vnd=0, shipping_vnd=28000, total_vnd=o.price_vnd * qty + 28000,
                      created_at=policy.now())
        order.items.append(OrderItem(offer_id=o.id, title_snapshot=o.product.title, variant_snapshot=o.variant.name,
                                     unit_price_vnd=o.price_vnd, qty=qty, discount_vnd=0))
        db.session.add(order)
        db.session.commit()
        return order
    return _make
