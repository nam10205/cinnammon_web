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
