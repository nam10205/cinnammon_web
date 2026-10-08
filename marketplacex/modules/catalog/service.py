from __future__ import annotations

from ...errors import NotFound, ValidationError
from ...events import publish
from ...extensions import db
from ..admin import policy
from ..audit import service as audit
from .models import Category, Offer, Product, Variant

PRODUCT_STATUSES = ("draft", "pending", "active", "rejected", "suspended")


def create_product(shop, category, title: str, brand: str, description: str, attributes: dict,
                   variants: list[dict], image_url: str | None = None, image_vector=None,
                   status: str = "draft", created_at=None) -> Product:
    from ..inventory import service as inventory
    p = Product(shop_id=shop.id, category_id=category.id, title=title, brand=brand, description=description,
                attributes=attributes or {}, image_url=image_url,
                image_vector=list(image_vector) if image_vector else None, status=status,
                created_at=created_at or policy.now())
    db.session.add(p)
    db.session.flush()
    for v in variants:
        var = Variant(product_id=p.id, name=v["name"], sku=v.get("sku"))
        db.session.add(var)
        db.session.flush()
        o = Offer(shop_id=shop.id, variant_id=var.id, price_vnd=int(v["price_vnd"]),
                  original_price_vnd=v.get("original_price_vnd"), purchase_limit=int(v.get("purchase_limit", 10)),
                  sold_count=int(v.get("sold_count", 0)), rating_avg=float(v.get("rating_avg", 0.0)))
        db.session.add(o)
        db.session.flush()
        inventory.init_ledger(o.id, int(v.get("stock", 0)))
    db.session.commit()
    return p


def set_status(product: Product, status: str, actor=None, reason: str | None = None) -> Product:
    if status not in PRODUCT_STATUSES:
        raise ValidationError("Unknown product status")
    before = product.status
    product.status = status
    if status in ("rejected", "suspended") or reason:
        product.moderation_reason = reason
    if actor is not None:
        audit.record(actor, f"listing.{status}", "product", product.id, reason, {"status": before}, {"status": status})
    publish("ProductChanged", product.id, {"product_id": product.id, "status": status})
    db.session.commit()
    return product


def get_product(product_id: int) -> Product:
    p = db.session.get(Product, product_id)
    if p is None:
        raise NotFound("Product not found")
    return p


def get_offer(offer_id: int) -> Offer:
    o = db.session.get(Offer, offer_id)
    if o is None:
        raise NotFound("Offer not found")
    return o


def get_category(category_id: int) -> Category:
    c = db.session.get(Category, category_id)
    if c is None:
        raise NotFound("Category not found")
    return c


def category_tree() -> list[Category]:
    return Category.query.filter_by(parent_id=None).order_by(Category.id).all()


def category_and_descendants(category: Category) -> list[int]:
    ids = [category.id]
    for c in category.children:
        ids.extend(category_and_descendants(c))
    return ids


def active_offers():
    return Offer.query.join(Variant).join(Product).filter(Product.status == "active")


def popular_offers(limit: int = 12) -> list[Offer]:
    return active_offers().order_by(Offer.sold_count.desc(), Offer.id).limit(limit).all()


def offers_in_categories(category_ids: list[int]) -> list[Offer]:
    return active_offers().filter(Product.category_id.in_(category_ids)).order_by(Offer.sold_count.desc()).all()


def offers_of_shop(shop_id: int, only_active: bool = True) -> list[Offer]:
    q = active_offers() if only_active else Offer.query.join(Variant).join(Product)
    return q.filter(Offer.shop_id == shop_id).order_by(Offer.id).all()


def delivery_promise(offer: Offer, city: str | None) -> str:
    if city and city.strip().lower() == offer.shop.location.lower():
        return "Delivery in 2–3 days"
    return "Delivery in 3–5 days"
