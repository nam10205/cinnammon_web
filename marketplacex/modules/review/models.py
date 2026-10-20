from __future__ import annotations

from ...extensions import db


class Review(db.Model):
    """Verified-purchase review; one per order item (BR06)."""
    id = db.Column(db.Integer, primary_key=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_item.id"), unique=True, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(1000), default="")
    seller_reply = db.Column(db.String(1000))
    status = db.Column(db.String(10), nullable=False, default="visible")
    created_at = db.Column(db.DateTime)
    customer = db.relationship("Account")
    order_item = db.relationship("OrderItem")
    __table_args__ = (db.CheckConstraint("rating BETWEEN 1 AND 5"),)
