from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from marketplacex.app import create_app
from marketplacex.extensions import db


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "SECRET_KEY": "t",
                      "GEMINI_API_KEY": ""})
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    yield app
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    return app.test_client()


class _Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, 0)

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr("marketplacex.clock.now", lambda: c.now)
    return c


def login_as(client, role, customer=None):
    with client.session_transaction() as s:
        s["role"] = role
        if customer is not None:
            s["customer_id"] = customer.id


@pytest.fixture
def demo(app):
    from marketplacex.modules.catalog.models import Category, Product, ProductImage
    from marketplacex.modules.identity.models import Address, Customer, FullName
    from marketplacex.modules.search.images import feature_vector, pack, solid_image

    phones, books = Category(name="Phones"), Category(name="Books")
    db.session.add_all([phones, books])

    def product(cat, title, brand, price, stock, rating, rgb=None):
        p = Product(category=cat, title=title, brand=brand, price=price, stock_quantity=stock, avg_rating=rating)
        if rgb:
            p.images.append(ProductImage(url=f"https://img.test/{title}.jpg",
                                         feature_vector=pack(feature_vector(solid_image(rgb)))))
        db.session.add(p)
        return p

    iphone = product(phones, "Apple iPhone 15", "Apple", 20_000_000, 5, 4.8, (220, 30, 30))
    galaxy = product(phones, "Samsung Galaxy S24", "Samsung", 15_000_000, 3, 4.5, (30, 30, 220))
    book = product(books, "Sách Đắc Nhân Tâm", "Unbranded", 100_000, 50, 4.9, (30, 200, 30))
    cheap = product(books, "Bookmark", "Unbranded", 20_000, 0, 4.0)

    def customer(email, names, phone, addr):
        c = Customer(email=email, phone_number=phone, full_name=FullName(
            first_name=names[0], middle_name=names[1], last_name=names[2]), address=Address(**addr))
        db.session.add(c)
        return c

    alice = customer("alice@demo", ("Alice", "", "Nguyen"), "0912345678",
                     dict(ward="Trang Tien", street="Trang Tien", detail="12, Hoan Kiem, Hanoi"))
    binh = customer("binh@demo", ("Binh", "Van", "Tran"), "0933111222",
                    dict(ward="Ben Nghe", street="Le Loi", detail="45, District 1, Ho Chi Minh City"))
    db.session.commit()
    return SimpleNamespace(phones=phones, books=books, iphone=iphone, galaxy=galaxy, book=book, cheap=cheap,
                           alice=alice, binh=binh)
