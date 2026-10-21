from __future__ import annotations

import urllib.request

from sqlalchemy.orm import selectinload

from ... import clock
from ...errors import NotFound, ValidationError
from ...extensions import db
from .models import Category, Product, ProductImage

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


def _int(value, message: str) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(message)
    if n < 0:
        raise ValidationError(message)
    return n


def save_product(product: Product | None, category_id: int, title: str, brand: str, description: str,
                 price: int, stock: int) -> Product:
    title = (title or "").strip()
    if not title or len(title) > 255:
        raise ValidationError("Title is required (255 characters max)")
    brand = (brand or "").strip() or "Unbranded"
    if len(brand) > 255:
        raise ValidationError("Brand is too long (255 characters max)")
    description = (description or "").strip()
    if len(description) > 255:
        raise ValidationError("Description is too long (255 characters max)")
    price = _int(price, "Price must be 0 or more")
    stock = _int(stock, "Stock must be 0 or more")
    get_category(category_id)
    now = clock.now()
    if product is None:
        product = Product(created_at=now)
        db.session.add(product)
    product.category_id = category_id
    product.title, product.brand, product.description = title, brand, description
    product.price, product.stock_quantity = price, stock
    product.updated_at = now
    db.session.commit()
    return product


def fetch_image(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read(5 * 1024 * 1024)


def add_image(product: Product, url: str, fetch=fetch_image) -> ProductImage:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")) or len(url) > 500:
        raise ValidationError("Enter an image URL starting with http(s)://")
    from ..search.images import feature_vector, pack
    try:
        vector = pack(feature_vector(fetch(url)))
    except Exception:
        vector = None
    image = ProductImage(product_id=product.id, url=url, feature_vector=vector)
    db.session.add(image)
    db.session.commit()
    return image


def remove_image(image_id: int) -> None:
    image = db.session.get(ProductImage, image_id)
    if image is None:
        raise NotFound("Image not found")
    db.session.delete(image)
    db.session.commit()


def seller_products(q: str = "", category_id: int | None = None, page: int = 1,
                    per_page: int = 50) -> tuple[list[Product], int]:
    query = db.session.query(Product)
    if q.strip():
        query = query.filter(Product.title.ilike(f"%{q.strip()}%"))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    total = query.count()
    items = (query.options(selectinload(Product.images)).order_by(Product.id.desc())
             .offset((max(1, page) - 1) * per_page).limit(per_page).all())
    return items, total


def save_category(category: Category | None, name: str, description: str) -> Category:
    name = (name or "").strip()
    description = (description or "").strip()
    if not name or len(name) > 255:
        raise ValidationError("Category name is required (255 characters max)")
    if len(description) > 255:
        raise ValidationError("Description is too long (255 characters max)")
    if category is None:
        category = Category()
        db.session.add(category)
    category.name, category.description = name, description
    db.session.commit()
    return category


def delete_category(category_id: int) -> None:
    category = get_category(category_id)
    if db.session.query(Product.id).filter(Product.category_id == category.id).first():
        raise ValidationError("Category still has products")
    db.session.delete(category)
    db.session.commit()
