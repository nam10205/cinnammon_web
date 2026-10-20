"""Inventory: reserve before payment, commit on confirmation, release on timeout/cancel (BR03)."""
from __future__ import annotations

from datetime import timedelta

from ...errors import InsufficientStock, NotFound, ValidationError
from ...events import publish
from ...extensions import db
from ..admin import policy
from .models import Reservation, StockLedger


def _sync(offer_ids) -> None:
    """Keep Product.stockQuantity in step with the ledgers (same transaction, no commit)."""
    from ..catalog import service as catalog
    catalog.sync_offers(offer_ids)


def init_ledger(offer_id: int, available: int) -> StockLedger:
    led = StockLedger(offer_id=offer_id, available=max(0, int(available)))
    db.session.add(led)
    db.session.flush()
    return led


def get_ledger(offer_id: int) -> StockLedger:
    led = StockLedger.query.filter_by(offer_id=offer_id).first()
    if led is None:
        raise NotFound("Stock ledger not found")
    return led


def in_stock(offer_id: int) -> int:
    led = StockLedger.query.filter_by(offer_id=offer_id).first()
    return led.available if led else 0


def set_stock(offer_id: int, available: int) -> None:
    if int(available) < 0:
        raise ValidationError("Stock cannot be negative")
    led = get_ledger(offer_id)
    led.available = int(available)
    led.version += 1
    publish("StockChanged", offer_id, {"offer_id": offer_id, "available": led.available})
    _sync([offer_id])
    db.session.commit()


def reserve(items: list[tuple[int, int]], attempt_id: str, ttl_min: int) -> list[Reservation]:
    existing = Reservation.query.filter_by(attempt_id=attempt_id).all()
    if existing:
        return existing
    merged: dict[int, int] = {}
    for oid, qty in items:
        merged[oid] = merged.get(oid, 0) + int(qty)
    from ..catalog.models import Offer
    for oid, qty in merged.items():
        led = get_ledger(oid)
        if qty <= 0 or led.available < qty:
            o = db.session.get(Offer, oid)
            title = o.product.title if o else f"offer {oid}"
            raise InsufficientStock(f"Not enough stock for {title} (available {led.available})")
    expires = policy.now() + timedelta(minutes=ttl_min)
    out = []
    for oid, qty in merged.items():
        led = get_ledger(oid)
        led.available -= qty
        led.reserved += qty
        led.version += 1
        r = Reservation(offer_id=oid, attempt_id=attempt_id, qty=qty, expires_at=expires)
        db.session.add(r)
        out.append(r)
    _sync(merged)
    db.session.commit()
    return out


def commit(attempt_id: str) -> None:
    rows = Reservation.query.filter_by(attempt_id=attempt_id, status="held").all()
    for r in rows:
        led = get_ledger(r.offer_id)
        led.reserved -= r.qty
        led.committed += r.qty
        led.version += 1
        r.status = "committed"
    _sync(r.offer_id for r in rows)
    db.session.commit()


def release(attempt_id: str, offer_ids: list[int] | None = None) -> None:
    q = Reservation.query.filter_by(attempt_id=attempt_id, status="held")
    if offer_ids is not None:
        q = q.filter(Reservation.offer_id.in_(offer_ids))
    rows = q.all()
    for r in rows:
        led = get_ledger(r.offer_id)
        led.reserved -= r.qty
        led.available += r.qty
        led.version += 1
        r.status = "released"
    _sync(r.offer_id for r in rows)
    db.session.commit()


def return_committed(offer_id: int, qty: int) -> None:
    led = get_ledger(offer_id)
    q = min(int(qty), led.committed)
    led.committed -= q
    led.available += q
    led.version += 1
    _sync([offer_id])
    db.session.commit()


def sweep_expired() -> list[str]:
    now = policy.now()
    rows = Reservation.query.filter(Reservation.status == "held", Reservation.expires_at < now).all()
    attempts = sorted({r.attempt_id for r in rows})
    for a in attempts:
        release(a)
    return attempts
