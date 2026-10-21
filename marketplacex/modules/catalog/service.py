from __future__ import annotations

from ...errors import NotFound, ValidationError
from ...events import publish
from ...extensions import db
from ..admin import policy
from ..audit import service as audit
from .models import Category, Offer, Product, ProductImage, Variant

PRODUCT_STATUSES = ("draft", "pending", "active", "rejected", "suspended")


TITLE_MAX = 255
BRAND_MAX = 255
DESCRIPTION_MAX = 255


def _fit_description(text: str | None) -> str:
    text = text or ""
    return text if len(text) <= DESCRIPTION_MAX else text[:DESCRIPTION_MAX - 3] + "..."


def sync_product(product: Product) -> None:
    """Recompute the derived ERD fields price, stockQuantity and avgRating.

    Flushes the session so pending offers, ledgers and reviews are visible, but never commits.
    """
    from ..inventory import service as inventory
    from ..review.models import Review
    db.session.flush()
    offers = Offer.query.join(Variant).filter(Variant.product_id == product.id).all()
    product.price = min((o.price_vnd for o in offers), default=0)
    product.stock_quantity = sum(inventory.in_stock(o.id) for o in offers)
    ratings = [r for (r,) in db.session.query(Review.rating)
               .filter(Review.product_id == product.id, Review.status == "visible").all()]
    product.avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else _offer_rating(offers)
    product.updated_at = policy.now()


def _offer_rating(offers) -> float:
    """avgRating without visible reviews: count-weighted offer ratings, else the mean of rated offers."""
    count = sum(o.rating_count for o in offers)
    if count:
        return round(sum(o.rating_avg * o.rating_count for o in offers) / count, 1)
    rated = [o.rating_avg for o in offers if o.rating_avg]
    return round(sum(rated) / len(rated), 1) if rated else 0


def sync_offers(offer_ids) -> None:
    """sync_product for every product owning one of these offers. Does not commit."""
    ids = set(offer_ids)
    if not ids:
        return
    # No DISTINCT over Product: Postgres cannot compare its JSON columns.
    owners = db.session.query(Variant.product_id).join(Offer).filter(Offer.id.in_(ids))
    for p in Product.query.filter(Product.id.in_(owners)).all():
        sync_product(p)


def create_product(shop, category, title: str, brand: str, description: str, attributes: dict,
                   variants: list[dict], image_urls: list[str] | None = None,
                   vectors: list[bytes | None] | None = None,
                   status: str = "draft", created_at=None, commit: bool = True) -> Product:
    """Create a product with its images, variants, offers and stock ledgers.

    The rows are linked through relationships and never flushed here, so `commit=False` lets a bulk
    seed insert many products in one flush (one round trip per table on Postgres).
    """
    from ..inventory.models import StockLedger
    created = created_at or policy.now()
    p = Product(shop_id=shop.id, category_id=category.id, title=title, brand=brand,
                description=_fit_description(description), attributes=attributes or {}, status=status,
                created_at=created, updated_at=created)
    db.session.add(p)
    vectors = vectors or []
    for i, url in enumerate(image_urls or []):
        p.images.append(ProductImage(url=url, sort_order=i, feature_vector=vectors[i] if i < len(vectors) else None))
    offers, stock = [], 0
    for v in variants:
        var = Variant(name=v["name"], sku=v.get("sku"))
        p.variants.append(var)
        o = Offer(shop_id=shop.id, price_vnd=int(v["price_vnd"]),
                  original_price_vnd=v.get("original_price_vnd"), purchase_limit=int(v.get("purchase_limit", 10)),
                  sold_count=int(v.get("sold_count", 0)), rating_avg=float(v.get("rating_avg", 0.0)),
                  rating_count=int(v.get("rating_count", 0)), base_rating_avg=float(v.get("rating_avg", 0.0)))
        var.offer = o
        available = max(0, int(v.get("stock", 0)))
        db.session.add(StockLedger(offer=o, available=available))
        offers.append(o)
        stock += available
    # The derived ERD fields sync_product would compute (a new product has no reviews yet).
    p.price = min((o.price_vnd for o in offers), default=0)
    p.stock_quantity = stock
    p.avg_rating = _offer_rating(offers)
    if commit:
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


# --- Listing publication (UC03, FR22) -------------------------------------------------------------

def _length_errors(title: str | None, brand: str | None, description: str | None) -> list[str]:
    errors = []
    if len(title or "") > TITLE_MAX:
        errors.append("Title must be 255 characters or fewer")
    if len(brand or "") > BRAND_MAX:
        errors.append("Brand must be 255 characters or fewer")
    if len(description or "") > DESCRIPTION_MAX:
        errors.append("Description must be 255 characters or fewer")
    return errors


def validate_listing(category, title: str, description: str, attributes: dict, variants: list[dict],
                     shop=None, brand: str | None = None) -> list[str]:
    errors = []
    if shop is not None and shop.verification_status != "verified":
        errors.append("Only verified shops can publish listings")
    if not (title or "").strip():
        errors.append("Title is required")
    errors.extend(_length_errors(title, brand, description))
    for attr in (category.attribute_schema or []):
        if not str((attributes or {}).get(attr, "")).strip():
            errors.append(f"Required attribute '{attr}' is missing")
    terms = [t.strip().lower() for t in policy.get_str("prohibited_terms").split(",") if t.strip()]
    text = f"{title} {description}".lower()
    for t in terms:
        if t in text:
            errors.append(f"Prohibited term '{t}' is not allowed")
    if not variants:
        errors.append("At least one variant is required")
    names = [str(v.get("name", "")).strip().lower() for v in variants]
    if any(not n for n in names):
        errors.append("Every variant needs a name")
    if len(set(names)) != len(names):
        errors.append("Duplicate variant names")
    for v in variants:
        price = int(v.get("price_vnd") or 0)
        if price <= 0:
            errors.append(f"Variant '{v.get('name')}': price must be greater than 0")
        orig = v.get("original_price_vnd")
        if orig not in (None, "") and int(orig) < price:
            errors.append(f"Variant '{v.get('name')}': original price cannot be below the selling price")
        if int(v.get("stock") or 0) < 0:
            errors.append(f"Variant '{v.get('name')}': stock cannot be negative")
    return errors


def save_listing(seller, shop_id: int, data: dict, product_id: int | None = None, submit: bool = False) -> Product:
    from ..inventory import service as inventory
    from ..seller import service as seller_service
    shop = seller_service.owned_shop(seller, shop_id)
    category = get_category(int(data["category_id"]))
    title = (data.get("title") or "").strip()
    description = data.get("description") or ""
    attributes = {k: v for k, v in (data.get("attributes") or {}).items() if str(k).strip()}
    variants = data.get("variants") or []
    if submit:
        errors = validate_listing(category, title, description, attributes, variants, shop, data.get("brand", ""))
        if errors:
            raise ValidationError("; ".join(errors))
    elif not title:
        raise ValidationError("Title is required")
    elif errors := _length_errors(title, data.get("brand", ""), description):
        raise ValidationError("; ".join(errors))
    if product_id is None:
        p = create_product(shop, category, title, data.get("brand", ""), description, attributes, variants, status="draft")
        if submit:
            set_status(p, "pending", seller, "Submitted for moderation")
        return p
    p = get_product(product_id)
    if p.shop_id != shop.id:
        raise NotFound("Product not found")
    content_changed = (p.title, p.description, p.attributes, p.category_id, p.brand) != (
        title, description, attributes, category.id, data.get("brand", ""))
    p.title, p.description, p.attributes, p.category_id, p.brand = title, description, attributes, category.id, data.get("brand", "")
    existing = {v.name.lower(): v for v in p.variants}
    for v in variants:
        var = existing.get(str(v["name"]).strip().lower())
        if var is None:
            var = Variant(product_id=p.id, name=str(v["name"]).strip())
            db.session.add(var)
            db.session.flush()
            o = Offer(shop_id=shop.id, variant_id=var.id, price_vnd=int(v["price_vnd"]),
                      original_price_vnd=v.get("original_price_vnd") or None, purchase_limit=int(v.get("purchase_limit") or 10))
            db.session.add(o)
            db.session.flush()
            inventory.init_ledger(o.id, int(v.get("stock") or 0))
        else:
            o = var.offer
            o.price_vnd = int(v["price_vnd"])
            o.original_price_vnd = v.get("original_price_vnd") or None
            o.purchase_limit = int(v.get("purchase_limit") or o.purchase_limit)
            o.version += 1
            inventory.get_ledger(o.id).available = int(v.get("stock") or 0)
    sync_product(p)
    db.session.commit()
    if submit and (p.status in ("draft", "rejected") or (p.status == "active" and content_changed)):
        set_status(p, "pending", seller, "Submitted for moderation")
    return p


def products_of_shop(shop_id: int) -> list[Product]:
    return Product.query.filter_by(shop_id=shop_id).order_by(Product.id.desc()).all()


def pending_products() -> list[Product]:
    return Product.query.filter_by(status="pending").order_by(Product.id).all()
