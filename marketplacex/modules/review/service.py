"""Verified purchase reviews and seller responses (FR19, BR06)."""
from __future__ import annotations

from ...errors import NotEligible, NotFound, ValidationError
from ...extensions import db
from ..admin import policy
from ..audit import service as audit
from ..order.models import OrderItem
from .models import Review


def create_review(customer, order_item_id: int, rating, comment: str) -> Review:
    item = db.session.get(OrderItem, order_item_id)
    if item is None or item.order.customer_id != customer.id:
        raise NotFound("Order item not found")
    if item.order.status not in ("Delivered", "Completed"):
        raise NotEligible("You can review an item only after it is delivered")
    if Review.query.filter_by(order_item_id=order_item_id).first():
        raise NotEligible("You already reviewed this item")
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise ValidationError("Rating must be 1 to 5 stars")
    if not 1 <= rating <= 5:
        raise ValidationError("Rating must be 1 to 5 stars")
    offer = item.offer
    r = Review(order_item_id=item.id, product_id=offer.product.id, shop_id=offer.shop_id, customer_id=customer.id,
               rating=rating, comment=(comment or "").strip()[:1000], created_at=policy.now())
    db.session.add(r)
    offer.rating_avg = round((offer.rating_avg * offer.rating_count + rating) / (offer.rating_count + 1), 2)
    offer.rating_count += 1
    db.session.commit()
    return r


def get_review(review_id: int) -> Review:
    r = db.session.get(Review, review_id)
    if r is None:
        raise NotFound("Review not found")
    return r


def reply(seller, review_id: int, text: str) -> Review:
    r = get_review(review_id)
    if r.order_item.order.shop.owner_id != seller.id:
        raise NotFound("Review not found")
    if not (text or "").strip():
        raise ValidationError("Reply cannot be empty")
    r.seller_reply = text.strip()[:1000]
    db.session.commit()
    return r


def set_hidden(actor, review_id: int, hidden: bool, reason: str) -> Review:
    if not (reason or "").strip():
        raise ValidationError("Reason is required")
    r = get_review(review_id)
    before = r.status
    r.status = "hidden" if hidden else "visible"
    audit.record(actor, "review.hide" if hidden else "review.show", "review", r.id, reason,
                 {"status": before}, {"status": r.status})
    db.session.commit()
    return r


def reviews_for_product(product_id: int) -> list[Review]:
    return Review.query.filter_by(product_id=product_id, status="visible").order_by(Review.id.desc()).all()


def reviews_for_shop(shop_id: int) -> list[Review]:
    return Review.query.filter_by(shop_id=shop_id).order_by(Review.id.desc()).all()


def low_rated(limit: int = 50) -> list[Review]:
    return Review.query.filter(Review.rating <= 2).order_by(Review.id.desc()).limit(limit).all()
