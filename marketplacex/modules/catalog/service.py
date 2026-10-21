from __future__ import annotations

from sqlalchemy.orm import selectinload

from ...errors import NotFound
from ...extensions import db
from .models import Category, Product

SORTS = ("rating", "price_asc", "price_desc", "newest")

_ORDER = {
    "rating": (Product.avg_rating.desc(), Product.id),
    "price_asc": (Product.price.asc(), Product.id),
    "price_desc": (Product.price.desc(), Product.id),
    "newest": (Product.created_at.desc(), Product.id.desc()),
}


def categories() -> list[Category]:
    return db.session.query(Category).order_by(Category.id).all()


def home_sections(per_category: int = 8) -> list[tuple[Category, list[Product]]]:
    out = []
    for c in categories():
        items = (db.session.query(Product).options(selectinload(Product.images))
                 .filter(Product.category_id == c.id)
                 .order_by(Product.avg_rating.desc(), Product.id).limit(per_category).all())
        if items:
            out.append((c, items))
    return out


def category_products(category_id: int, sort: str = "rating", min_price: int | None = None,
                      max_price: int | None = None, page: int = 1,
                      per_page: int = 24) -> tuple[list[Product], int]:
    q = db.session.query(Product).filter(Product.category_id == category_id)
    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)
    total = q.count()
    page = max(1, page)
    items = (q.options(selectinload(Product.images))
             .order_by(*_ORDER.get(sort, _ORDER["rating"]))
             .offset((page - 1) * per_page).limit(per_page).all())
    return items, total


def get_product(product_id: int) -> Product:
    p = db.session.get(Product, product_id)
    if p is None:
        raise NotFound("Product not found")
    return p


def get_category(category_id: int) -> Category:
    c = db.session.get(Category, category_id)
    if c is None:
        raise NotFound("Category not found")
    return c
