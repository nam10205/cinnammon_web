from __future__ import annotations

from ...extensions import db


class PaymentAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, index=True, nullable=False)
    attempt_id = db.Column(db.String(64), unique=True, nullable=False)
    amount_vnd = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending|authorized|captured|failed|voided
    provider_ref = db.Column(db.String(40), unique=True, nullable=False)
    captured_vnd = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime)


class Refund(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payment_attempt.id"), nullable=False)
    return_case_id = db.Column(db.Integer)
    amount_vnd = db.Column(db.Integer, nullable=False)
    idempotency_key = db.Column(db.String(64), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    provider_ref = db.Column(db.String(40))
    created_at = db.Column(db.DateTime)


class ProviderCallback(db.Model):
    """Replay cache: each provider event id is processed once (report §11)."""
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(64), unique=True, nullable=False)
    provider_ref = db.Column(db.String(40))
    status = db.Column(db.String(20))
    received_at = db.Column(db.DateTime)
