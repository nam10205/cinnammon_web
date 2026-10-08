from __future__ import annotations

from ...extensions import db


class CheckoutGroup(db.Model):
    """Checkout attempt and orchestration state (report §7 Checkout component)."""
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    attempt_id = db.Column(db.String(64), unique=True, nullable=False)
    idempotency_key = db.Column(db.String(64))
    address_id = db.Column(db.Integer, db.ForeignKey("address.id"))
    voucher_codes = db.Column(db.JSON, default=list)
    quote_payload = db.Column(db.JSON, nullable=False)
    quote_hash = db.Column(db.String(64), nullable=False)
    quote_expires_at = db.Column(db.DateTime, nullable=False)
    cart_version = db.Column(db.Integer)
    status = db.Column(db.String(20), nullable=False, default="quoted")  # quoted|placing|completed|failed
    merchandise_vnd = db.Column(db.Integer, nullable=False, default=0)
    discount_vnd = db.Column(db.Integer, nullable=False, default=0)
    shipping_vnd = db.Column(db.Integer, nullable=False, default=0)
    total_vnd = db.Column(db.Integer, nullable=False, default=0)
    failure_reason = db.Column(db.String(300))
    created_at = db.Column(db.DateTime)
    __table_args__ = (db.UniqueConstraint("customer_id", "idempotency_key"),)
