"""Payment: authorize, verified callbacks, void and bounded refunds (FR13, BR07)."""
from __future__ import annotations

import uuid

from flask import current_app
from sqlalchemy import func

from ...adapters.payment_provider import FakePaymentProvider
from ...errors import InvalidSignature, NotFound, RefundExceedsCaptured, ValidationError
from ...events import publish
from ...extensions import db
from ..admin import policy
from .models import PaymentAttempt, ProviderCallback, Refund

FINAL = {"captured", "failed", "voided"}


def provider() -> FakePaymentProvider:
    return FakePaymentProvider(current_app.config["PAYMENT_WEBHOOK_SECRET"])


def get_payment(payment_id: int) -> PaymentAttempt:
    p = db.session.get(PaymentAttempt, payment_id)
    if p is None:
        raise NotFound("Payment not found")
    return p


def authorize(group_id: int, amount_vnd: int, attempt_id: str) -> PaymentAttempt:
    existing = PaymentAttempt.query.filter_by(attempt_id=attempt_id).first()
    if existing:
        return existing
    ref = provider().authorize(amount_vnd, attempt_id)
    p = PaymentAttempt(group_id=group_id, attempt_id=attempt_id, amount_vnd=amount_vnd, status="pending",
                       provider_ref=ref, created_at=policy.now())
    db.session.add(p)
    db.session.commit()
    return p


def simulate(payment_id: int, outcome: str) -> dict:
    p = get_payment(payment_id)
    payload = {"event_id": "evt_" + uuid.uuid4().hex[:12], "provider_ref": p.provider_ref,
               "status": "authorized" if outcome == "success" else "failed"}
    return {"payload": payload, "signature": provider().sign(payload)}


def handle_callback(payload: dict, signature: str) -> PaymentAttempt:
    if not provider().verify(payload, signature):
        raise InvalidSignature("Callback signature verification failed")
    p = PaymentAttempt.query.filter_by(provider_ref=payload.get("provider_ref")).first()
    if p is None:
        raise NotFound("Unknown provider reference")
    if ProviderCallback.query.filter_by(event_id=payload.get("event_id")).first():
        return p  # replay: already processed
    db.session.add(ProviderCallback(event_id=payload.get("event_id"), provider_ref=p.provider_ref,
                                    status=payload.get("status"), received_at=policy.now()))
    if p.status in FINAL:
        db.session.commit()
        return p
    if payload.get("status") == "authorized":
        # Demo provider authorizes and captures in one step.
        p.status = "captured"
        p.captured_vnd = p.amount_vnd
        publish("PaymentAuthorized", p.group_id, {"group_id": p.group_id, "payment_id": p.id})
    elif payload.get("status") == "failed":
        p.status = "failed"
        publish("PaymentChanged", p.group_id, {"group_id": p.group_id, "payment_id": p.id, "status": "failed"})
    else:
        raise ValidationError("Unknown payment status")
    db.session.commit()
    return p


def void(payment_id: int) -> None:
    p = get_payment(payment_id)
    if p.status in ("pending", "authorized"):
        provider().void(p.provider_ref)
        p.status = "voided"
        publish("PaymentChanged", p.group_id, {"group_id": p.group_id, "payment_id": p.id, "status": "voided"})
        db.session.commit()


def captured_for_group(group_id: int) -> PaymentAttempt | None:
    return PaymentAttempt.query.filter_by(group_id=group_id, status="captured").first()


def latest_for_group(group_id: int) -> PaymentAttempt | None:
    return PaymentAttempt.query.filter_by(group_id=group_id).order_by(PaymentAttempt.id.desc()).first()


def is_captured(group_id: int) -> bool:
    return captured_for_group(group_id) is not None


def refunded_vnd(payment_id: int) -> int:
    return db.session.query(func.coalesce(func.sum(Refund.amount_vnd), 0)).filter(
        Refund.payment_id == payment_id, Refund.status == "succeeded").scalar()


def refunded_for_order(order_id: int) -> int:
    return db.session.query(func.coalesce(func.sum(Refund.amount_vnd), 0)).filter(
        Refund.order_id == order_id, Refund.status == "succeeded").scalar()


def refundable_vnd(payment_id: int) -> int:
    p = get_payment(payment_id)
    return p.captured_vnd - refunded_vnd(payment_id)


def refund(payment_id: int, amount_vnd: int, idempotency_key: str, return_case_id: int | None = None,
           order_id: int | None = None) -> Refund:
    existing = Refund.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return existing
    amount_vnd = int(amount_vnd)
    if amount_vnd <= 0:
        raise ValidationError("Refund amount must be positive")
    p = get_payment(payment_id)
    if amount_vnd > refundable_vnd(payment_id):
        raise RefundExceedsCaptured(
            f"Refund {amount_vnd:,} ₫ exceeds refundable {refundable_vnd(payment_id):,} ₫")
    ref = provider().refund(p.provider_ref, amount_vnd, idempotency_key)
    r = Refund(payment_id=p.id, return_case_id=return_case_id, order_id=order_id, amount_vnd=amount_vnd,
               idempotency_key=idempotency_key, status="succeeded", provider_ref=ref, created_at=policy.now())
    db.session.add(r)
    db.session.flush()
    publish("PaymentChanged", p.group_id, {"kind": "refund", "group_id": p.group_id, "refund_id": r.id,
                                           "return_case_id": return_case_id, "order_id": order_id, "amount_vnd": amount_vnd,
                                           "status": "refunded"})
    db.session.commit()
    return r
