from __future__ import annotations

from datetime import datetime

from ...extensions import db


class Cart(db.Model):
    """Versioned customer cart; 0..1 active cart per customer (report §8.1)."""
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    items = db.relationship("CartItem", backref="cart", order_by="CartItem.id", cascade="all, delete-orphan")


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey("cart.id"), nullable=False)
    offer_id = db.Column(db.Integer, db.ForeignKey("offer.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    selected = db.Column(db.Boolean, nullable=False, default=True)
    offer = db.relationship("Offer")
    __table_args__ = (db.UniqueConstraint("cart_id", "offer_id"), db.CheckConstraint("qty > 0"))


class SavedItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # product | shop
    target_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("customer_id", "kind", "target_id"),)


class RecentSearch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    query_text = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
