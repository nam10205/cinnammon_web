from __future__ import annotations

from ...extensions import db


class Order(db.Model):
    """One shop-specific order inside a checkout group (FR11). Snapshots preserve terms as purchased."""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, index=True, nullable=False)
    attempt_id = db.Column(db.String(64), index=True, nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)
    address_snapshot = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Draft")
    merchandise_vnd = db.Column(db.Integer, nullable=False, default=0)
    discount_vnd = db.Column(db.Integer, nullable=False, default=0)
    shop_discount_vnd = db.Column(db.Integer, nullable=False, default=0)
    platform_discount_vnd = db.Column(db.Integer, nullable=False, default=0)
    shipping_vnd = db.Column(db.Integer, nullable=False, default=0)
    total_vnd = db.Column(db.Integer, nullable=False, default=0)
    delivered_at = db.Column(db.DateTime)
    cancel_from = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    items = db.relationship("OrderItem", backref="order", order_by="OrderItem.id", cascade="all, delete-orphan")
    history = db.relationship("OrderStatusHistory", order_by="OrderStatusHistory.id", cascade="all, delete-orphan")
    shop = db.relationship("Shop")
    customer = db.relationship("Account")


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    offer_id = db.Column(db.Integer, db.ForeignKey("offer.id"), nullable=False)
    title_snapshot = db.Column(db.String(200), nullable=False)
    variant_snapshot = db.Column(db.String(80), nullable=False)
    unit_price_vnd = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    discount_vnd = db.Column(db.Integer, nullable=False, default=0)  # total discount on this line
    offer = db.relationship("Offer")

    @property
    def line_total_vnd(self) -> int:
        return self.unit_price_vnd * self.qty - self.discount_vnd


class OrderStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    from_status = db.Column(db.String(30))
    to_status = db.Column(db.String(30), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("account.id"))
    reason = db.Column(db.String(500))
    at = db.Column(db.DateTime, nullable=False)
    actor = db.relationship("Account")
