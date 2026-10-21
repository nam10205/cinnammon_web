from __future__ import annotations

from ...extensions import db


class StockLedger(db.Model):
    """Available, reserved and committed quantity for one offer at the default location."""
    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("offer.id"), unique=True, nullable=False)
    location = db.Column(db.String(40), nullable=False, default="default")
    available = db.Column(db.Integer, nullable=False, default=0)
    reserved = db.Column(db.Integer, nullable=False, default=0)
    committed = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    offer = db.relationship("Offer")
    __table_args__ = (
        db.CheckConstraint("available >= 0", name="ck_available_nonneg"),
        db.CheckConstraint("reserved >= 0", name="ck_reserved_nonneg"),
        db.CheckConstraint("committed >= 0", name="ck_committed_nonneg"),
    )


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("offer.id"), nullable=False)
    attempt_id = db.Column(db.String(64), nullable=False, index=True)
    qty = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="held")
    __table_args__ = (db.UniqueConstraint("offer_id", "attempt_id"),)
