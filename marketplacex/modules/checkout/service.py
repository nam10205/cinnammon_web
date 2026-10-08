"""Checkout saga (report §9.2): quote -> place_order -> reserve -> risk -> authorize -> orders, with compensation."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import timedelta

from ...errors import DomainError, NotFound, QuoteChanged, QuoteExpired, ValidationError
from ...events import publish, subscribe
from ...extensions import db
from ..admin import policy
from ..cart import service as cart
from ..catalog import service as catalog
from ..identity.models import Address
from ..inventory import service as inventory
from ..logistics import service as logistics
from ..order import service as order_service
from ..payment import service as payment
from ..promotion import service as promo
from ..risk import service as risk
from .models import CheckoutGroup


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _spread(amount: int, items: list[dict]) -> None:
    weights = [it["unit_price_vnd"] * it["qty"] for it in items]
    total = sum(weights)
    for it, w in zip(items, weights):
        it["discount_vnd"] = amount * w // total if total else 0
    if items:
        items[0]["discount_vnd"] += amount - sum(it["discount_vnd"] for it in items)


def _address(customer, address_id) -> Address:
    a = db.session.get(Address, int(address_id)) if address_id else None
    if a is None or a.user_id != customer.id:
        raise ValidationError("Please choose a delivery address")
    return a


def _build(customer, address: Address, codes: list[str]) -> dict:
    """Server-side pricing; the client never supplies an authoritative total (BR02, §4.3)."""
    c = cart.get_cart(customer)
    shops: dict[int, list[dict]] = {}
    unavailable = []
    for ci in [i for i in c.items if i.selected]:
        o = ci.offer
        p = o.product
        stock = inventory.in_stock(o.id)
        if p.status != "active" or stock < ci.qty or ci.qty > o.purchase_limit:
            reason = "no longer available" if p.status != "active" else (
                "exceeds purchase limit" if ci.qty > o.purchase_limit else f"only {stock} in stock")
            unavailable.append({"offer_id": o.id, "title": p.title, "reason": reason})
            continue
        shops.setdefault(o.shop_id, []).append({
            "offer_id": o.id, "title": p.title, "variant": o.variant.name, "unit_price_vnd": o.price_vnd,
            "qty": ci.qty, "discount_vnd": 0})
    if not shops:
        raise ValidationError("Nothing to check out")
    subtotals = {sid: sum(i["unit_price_vnd"] * i["qty"] for i in items) for sid, items in shops.items()}
    shipping = logistics.quote(address, list(shops))
    ev = promo.evaluate(customer, subtotals, shipping, codes)
    lines = []
    for sid, items in shops.items():
        disc = ev.item_discounts.get(sid, 0)
        _spread(disc, items)
        ship = shipping[sid] - ev.shipping_discounts.get(sid, 0)
        lines.append({"shop_id": sid, "shop_name": catalog.get_offer(items[0]["offer_id"]).shop.name, "items": items,
                      "merchandise_vnd": subtotals[sid], "discount_vnd": disc,
                      "shop_discount_vnd": ev.shop_discounts.get(sid, 0),
                      "platform_discount_vnd": ev.platform_discounts.get(sid, 0),
                      "shipping_vnd": ship, "shipping_discount_vnd": ev.shipping_discounts.get(sid, 0),
                      "total_vnd": subtotals[sid] - disc + ship})
    return {"shops": lines, "unavailable": unavailable, "cart_version": c.version, "address_id": address.id,
            "codes": codes, "applied": [asdict(a) for a in ev.applied]}


def quote(customer, address_id: int, voucher_codes: list[str]) -> CheckoutGroup:
    sweep()
    address = _address(customer, address_id)
    codes = [c.strip().upper() for c in voucher_codes if c and c.strip()]
    payload = _build(customer, address, codes)
    lines = payload["shops"]
    g = CheckoutGroup(customer_id=customer.id, attempt_id=uuid.uuid4().hex, address_id=address.id, voucher_codes=codes,
                      quote_payload=payload, quote_hash=_hash(payload),
                      quote_expires_at=policy.now() + timedelta(minutes=policy.get_int("quote_ttl_min")),
                      cart_version=payload["cart_version"], status="quoted",
                      merchandise_vnd=sum(l["merchandise_vnd"] for l in lines),
                      discount_vnd=sum(l["discount_vnd"] for l in lines),
                      shipping_vnd=sum(l["shipping_vnd"] for l in lines),
                      total_vnd=sum(l["total_vnd"] for l in lines), created_at=policy.now())
    db.session.add(g)
    db.session.commit()
    return g


def get_group(customer, group_id: int) -> CheckoutGroup:
    g = db.session.get(CheckoutGroup, group_id)
    if g is None or g.customer_id != customer.id:
        raise NotFound("Checkout not found")
    return g


def _changed_items(old: dict, new: dict) -> list[dict]:
    def flat(p):
        return {i["offer_id"]: i for l in p["shops"] for i in l["items"]}
    o, n = flat(old), flat(new)
    changed = []
    for oid, item in o.items():
        if oid not in n:
            changed.append({"offer_id": oid, "title": item["title"], "change": "no longer available"})
        elif n[oid]["unit_price_vnd"] != item["unit_price_vnd"]:
            changed.append({"offer_id": oid, "title": item["title"],
                            "change": f"price {item['unit_price_vnd']:,} → {n[oid]['unit_price_vnd']:,} ₫"})
    return changed or [{"offer_id": None, "title": "Order totals", "change": "discounts or shipping changed"}]


def place_order(customer, group_id: int, idempotency_key: str, quote_hash: str) -> CheckoutGroup:
    if not idempotency_key:
        raise ValidationError("Missing idempotency key")
    prior = CheckoutGroup.query.filter_by(customer_id=customer.id, idempotency_key=idempotency_key).first()
    if prior is not None:
        return prior  # duplicate submission returns the original outcome
    g = get_group(customer, group_id)
    if g.status != "quoted":
        return g
    if policy.now() > g.quote_expires_at:
        raise QuoteExpired("Your quote expired. Please review the latest prices.")
    if quote_hash != g.quote_hash:
        raise QuoteChanged("The quote you confirmed does not match", [])
    address = _address(customer, g.address_id)
    try:
        fresh = _build(customer, address, g.voucher_codes or [])
    except DomainError as e:
        raise QuoteChanged(f"Your cart changed: {e.message}", [])
    if _hash(fresh) != g.quote_hash:
        raise QuoteChanged("Prices or availability changed since your quote", _changed_items(g.quote_payload, fresh))

    g.idempotency_key = idempotency_key
    g.status = "placing"
    db.session.commit()
    ttl = policy.get_int("reservation_ttl_min")
    try:
        items = [(i["offer_id"], i["qty"]) for l in g.quote_payload["shops"] for i in l["items"]]
        inventory.reserve(items, g.attempt_id, ttl)
        promo.reserve(customer, g.quote_payload["applied"], g.attempt_id, ttl)
        order_service.create_orders(g, g.quote_payload["shops"], address, customer)
        if risk.evaluate_checkout(customer, g) == "held":
            g.failure_reason = "Under risk review"
            db.session.commit()
        else:
            continue_after_risk(g)
    except DomainError as e:
        db.session.rollback()
        compensate(g, e.message)
        raise
    return g


def continue_after_risk(group: CheckoutGroup):
    group.failure_reason = None
    p = payment.authorize(group.id, group.total_vnd, group.attempt_id)
    db.session.commit()
    return p


def compensate(group: CheckoutGroup, reason: str, payment_failed: bool = False) -> None:
    if group.status in ("failed", "completed"):
        return
    inventory.release(group.attempt_id)
    promo.release(group.attempt_id)
    p = payment.latest_for_group(group.id)
    if p is not None and p.status == "pending":
        payment.void(p.id)
    for o in order_service.orders_of_group(group.id):
        if o.status in ("Draft", "PendingPayment"):
            order_service.transition(o, "PaymentFailed" if payment_failed else "Cancelled", None, reason)
    group.status = "failed"
    group.failure_reason = reason
    db.session.commit()


def sweep() -> None:
    for attempt in inventory.sweep_expired():
        g = CheckoutGroup.query.filter_by(attempt_id=attempt).first()
        if g is not None and g.status == "placing":
            compensate(g, "Reservation expired")


@subscribe("PaymentAuthorized", "checkout")
def _on_payment_authorized(event) -> None:
    g = db.session.get(CheckoutGroup, int(event.payload["group_id"]))
    if g is None or g.status == "completed":
        return
    if g.status == "failed":
        # Late capture after compensation: no captured money without an order (§4.3).
        p = payment.captured_for_group(g.id)
        if p is not None:
            payment.refund(p.id, payment.refundable_vnd(p.id), f"late-capture-{g.id}")
        return
    orders = order_service.orders_of_group(g.id)
    for o in orders:
        order_service.transition(o, "Confirmed", None, "Payment captured")
    inventory.commit(g.attempt_id)
    promo.commit(g.attempt_id, g.id)
    for o in orders:
        for it in o.items:
            it.offer.sold_count += it.qty
    from ..identity.models import User
    cart.remove_items(db.session.get(User, g.customer_id), [it.offer_id for o in orders for it in o.items])
    g.status = "completed"
    for o in orders:
        publish("OrderCreated", o.id, {"order_id": o.id, "customer_id": o.customer_id, "shop_id": o.shop_id})
    db.session.commit()


@subscribe("PaymentChanged", "checkout")
def _on_payment_changed(event) -> None:
    if event.payload.get("status") != "failed":
        return
    g = db.session.get(CheckoutGroup, int(event.payload["group_id"]))
    if g is not None:
        compensate(g, "Payment failed", payment_failed=True)
