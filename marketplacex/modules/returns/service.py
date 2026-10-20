"""Return, refund and dispute (UC05, FR17, FR18; report §9.3-9.4)."""
from __future__ import annotations

import os
import uuid
from datetime import timedelta

from flask import current_app

from ...errors import IllegalTransition, NotEligible, NotFound, RefundExceedsCaptured, ValidationError
from ...events import publish, subscribe
from ...extensions import db
from ..admin import policy
from ..audit import service as audit
from ..order import service as order_service
from ..payment import service as payment
from .models import DisputeDecision, Evidence, ReturnCase, ReturnCaseItem

OPEN_STATUSES = ("requested", "proposed", "accepted", "awaiting_return", "inspecting", "inspection_failed",
                 "seller_rejected", "disputed")
MAX_UPLOAD = 2 * 1024 * 1024
MAGIC = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg"}


def get_case(case_id: int) -> ReturnCase:
    c = db.session.get(ReturnCase, case_id)
    if c is None:
        raise NotFound("Case not found")
    return c


def case_for_customer(customer, case_id: int) -> ReturnCase:
    c = get_case(case_id)
    if c.customer_id != customer.id:
        raise NotFound("Case not found")
    return c


def case_for_seller(seller, case_id: int) -> ReturnCase:
    c = get_case(case_id)
    if c.order.shop.owner_id != seller.id:
        raise NotFound("Case not found")
    return c


def cases_for_order(order_id: int) -> list[ReturnCase]:
    return ReturnCase.query.filter_by(order_id=order_id).order_by(ReturnCase.id).all()


def cases_for_shop(shop_id: int) -> list[ReturnCase]:
    from ..order.models import Order
    return ReturnCase.query.join(Order).filter(Order.shop_id == shop_id).order_by(ReturnCase.id.desc()).all()


def open_cases() -> list[ReturnCase]:
    return ReturnCase.query.filter(ReturnCase.status.in_(OPEN_STATUSES)).order_by(ReturnCase.id).all()


def _note(case: ReturnCase, author, kind: str, content: str) -> None:
    db.session.add(Evidence(case_id=case.id, author_id=getattr(author, "id", None), kind=kind,
                            content=content[:1000], at=policy.now()))


def _set_status(case: ReturnCase, status: str, actor, note: str) -> None:
    before = case.status
    case.status = status
    _note(case, actor, "system", f"Status: {status}. {note}".strip())
    audit.record(actor, f"return.{status}", "return_case", case.id, note, {"status": before}, {"status": status})
    publish("ReturnStatusChanged", case.id, {"case_id": case.id, "order_id": case.order_id, "status": status,
                                             "customer_id": case.customer_id, "shop_id": case.order.shop_id})


def _returned_qty(order_item_id: int, exclude_case: int | None = None) -> int:
    q = ReturnCaseItem.query.join(ReturnCase).filter(ReturnCaseItem.order_item_id == order_item_id,
                                                     ReturnCase.status.notin_(["closed"]))
    if exclude_case:
        q = q.filter(ReturnCase.id != exclude_case)
    return sum(i.qty for i in q.all())


def check_eligibility(customer, order, items: dict[int, int]) -> None:
    if order.customer_id != customer.id:
        raise NotFound("Order not found")
    if order.status not in ("Delivered", "Completed", "ReturnRequested") or order.delivered_at is None:
        raise NotEligible("Order is not delivered")
    if policy.now() > order.delivered_at + timedelta(days=policy.get_int("return_window_days")):
        raise NotEligible("Return window has closed")
    if not items or all(q <= 0 for q in items.values()):
        raise NotEligible("Choose at least one item to return")
    by_id = {i.id: i for i in order.items}
    for item_id, qty in items.items():
        it = by_id.get(int(item_id))
        if it is None:
            raise NotFound("Item not found")
        if qty < 0 or _returned_qty(it.id) + qty > it.qty:
            raise NotEligible("Quantity exceeds purchased")
        if qty and ReturnCaseItem.query.join(ReturnCase).filter(
                ReturnCaseItem.order_item_id == it.id, ReturnCase.status.in_(OPEN_STATUSES)).first():
            raise NotEligible("An open case already exists for this item")


def save_evidence_image(file) -> str:
    data = file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise ValidationError("Evidence images must be 2 MB or smaller")
    ext = next((e for m, e in MAGIC.items() if data.startswith(m)), None)
    if ext is None:
        raise ValidationError("Evidence must be a PNG or JPEG image")
    folder = current_app.config["UPLOAD_DIR"]
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(folder, name), "wb") as fh:
        fh.write(data)
    return f"/static/uploads/{name}"


def open_case(customer, order_id: int, items: dict[int, int], reason: str, remedy: str, statement: str,
              image=None) -> ReturnCase:
    order = order_service.get_for_customer(customer, order_id)
    items = {int(k): int(v) for k, v in items.items() if int(v) > 0}
    if remedy not in ("refund_only", "return_and_refund"):
        raise ValidationError("Choose a remedy")
    if not (reason or "").strip():
        raise ValidationError("Reason is required")
    check_eligibility(customer, order, items)
    image_url = save_evidence_image(image) if image is not None and getattr(image, "filename", "") else None
    c = ReturnCase(order_id=order.id, customer_id=customer.id, reason=reason.strip()[:200], remedy=remedy,
                   status="requested", created_at=policy.now(),
                   seller_deadline=policy.now() + timedelta(hours=policy.get_int("seller_response_hours")))
    for item_id, qty in items.items():
        c.items.append(ReturnCaseItem(order_item_id=item_id, qty=qty))
    db.session.add(c)
    db.session.flush()
    _note(c, customer, "statement", (statement or reason).strip())
    if image_url:
        _note(c, customer, "image", image_url)
    if order.status != "ReturnRequested":
        order_service.transition(order, "ReturnRequested", customer, f"Return case #{c.id}: {reason}")
    _set_status(c, "requested", customer, f"Seller must respond by {c.seller_deadline:%Y-%m-%d %H:%M}")
    db.session.commit()
    return c


def add_evidence(user, case_id: int, statement: str, image=None) -> ReturnCase:
    c = get_case(case_id)
    if user.id not in (c.customer_id, c.order.shop.owner_id) and user.role != "admin":
        raise NotFound("Case not found")
    if statement and statement.strip():
        _note(c, user, "statement", statement.strip())
    if image is not None and getattr(image, "filename", ""):
        _note(c, user, "image", save_evidence_image(image))
    db.session.commit()
    return c


def refund_amount(case: ReturnCase) -> int:
    order = case.order
    total = 0
    full = True
    for ci in case.items:
        it = ci.order_item
        total += it.unit_price_vnd * ci.qty - it.discount_vnd * ci.qty // it.qty
    for it in order.items:
        if _returned_qty(it.id, exclude_case=case.id) + sum(ci.qty for ci in case.items if ci.order_item_id == it.id) < it.qty:
            full = False
    if full:
        total += order.shipping_vnd
    return total


def execute_refund(case: ReturnCase, amount_vnd: int | None = None, actor=None):
    amount = refund_amount(case) if amount_vnd is None else int(amount_vnd)
    p = payment.captured_for_group(case.order.group_id)
    if p is None:
        raise NotEligible("No captured payment to refund")
    order_left = case.order.total_vnd - payment.refunded_for_order(case.order_id)
    if amount > order_left:
        # BR07 per order: never refund more than this shop order is worth.
        raise RefundExceedsCaptured(f"Refund {amount:,} ₫ exceeds what remains on order #{case.order_id} ({order_left:,} ₫)")
    r = payment.refund(p.id, amount, f"return-{case.id}", case.id, order_id=case.order_id)
    case.refund_amount_vnd = amount
    case.pending_amount_vnd = None
    _set_status(case, "refunded", actor, f"Refunded {amount:,} ₫ (ref {r.provider_ref})")
    _settle_order(case.order, actor)
    db.session.commit()
    return r


def _settle_order(order, actor) -> None:
    """Move the order out of ReturnRequested only once every case on it is finished."""
    if order.status != "ReturnRequested":
        return
    cases = cases_for_order(order.id)
    if any(c.status in OPEN_STATUSES for c in cases):
        return
    if any(c.status == "refunded" for c in cases):
        order_service.transition(order, "Refunded", actor, "All return cases resolved with a refund")
    else:
        order_service.transition(order, "Rejected", actor, "All return cases closed without a refund")


def seller_respond(seller, case_id: int, action: str, reason: str, amount_vnd: int | None = None) -> ReturnCase:
    c = case_for_seller(seller, case_id)
    if c.status != "requested":
        raise IllegalTransition("This case is not waiting for a seller response")
    if not (reason or "").strip():
        raise ValidationError("Reason is required")
    c.seller_response = reason.strip()
    _note(c, seller, "statement", reason.strip())
    if action == "accept":
        if c.remedy == "refund_only":
            _set_status(c, "accepted", seller, "Seller accepted a refund without return")
            execute_refund(c, actor=seller)
        else:
            from ..logistics import service as logistics
            _set_status(c, "awaiting_return", seller, "Seller accepted; return label issued")
            logistics.create_shipment(c.order, 0, kind="return", return_case=c)
    elif action == "propose":
        if not amount_vnd or not 0 < int(amount_vnd) <= refund_amount(c):
            raise ValidationError(f"Proposed amount must be between 1 and {refund_amount(c):,} ₫")
        c.proposed_amount_vnd = int(amount_vnd)
        _set_status(c, "proposed", seller, f"Seller proposed a refund of {int(amount_vnd):,} ₫")
    elif action == "reject":
        _set_status(c, "seller_rejected", seller, "Seller rejected the request")
    else:
        raise ValidationError("Unknown action")
    db.session.commit()
    return c


def accept_proposal(customer, case_id: int) -> ReturnCase:
    c = case_for_customer(customer, case_id)
    if c.status != "proposed":
        raise IllegalTransition("There is no proposal to accept")
    execute_refund(c, c.proposed_amount_vnd, actor=customer)
    return c


@subscribe("TrackingChanged", "returns")
def _on_tracking(event) -> None:
    p = event.payload
    if p.get("kind") == "return" and p.get("status") == "delivered" and p.get("return_case_id"):
        c = get_case(int(p["return_case_id"]))
        if c.status == "awaiting_return":
            _set_status(c, "inspecting", None, "Return parcel arrived at the seller")


def inspect(seller, case_id: int, passed: bool, note: str) -> ReturnCase:
    c = case_for_seller(seller, case_id)
    if c.status != "inspecting":
        raise IllegalTransition("The returned item has not arrived yet")
    c.inspection_result = ("passed" if passed else "failed") + (f": {note}" if note else "")
    if passed:
        from ..inventory import service as inventory
        for ci in c.items:
            inventory.return_committed(ci.order_item.offer_id, ci.qty)
        execute_refund(c, actor=seller)
    else:
        _set_status(c, "inspection_failed", seller, note or "Inspection failed")
    db.session.commit()
    return c


def can_escalate(case: ReturnCase) -> bool:
    if case.status in ("seller_rejected", "inspection_failed", "proposed"):
        return True
    return case.status == "requested" and case.seller_deadline is not None and policy.now() > case.seller_deadline


def escalate(customer, case_id: int, statement: str) -> ReturnCase:
    c = case_for_customer(customer, case_id)
    if not can_escalate(c):
        raise NotEligible("This case cannot be escalated yet")
    if statement and statement.strip():
        _note(c, customer, "statement", statement.strip())
    _set_status(c, "disputed", customer, "Escalated to platform dispute review")
    db.session.commit()
    return c


def decide_dispute(agent, case_id: int, outcome: str, reason_code: str, amount_vnd: int | None, note: str) -> DisputeDecision:
    c = get_case(case_id)
    if c.decision is not None or c.status != "disputed":
        raise NotEligible("This dispute has already been decided or is not under review")
    if not (reason_code or "").strip():
        raise ValidationError("Reason code is required")
    if outcome not in ("refund_customer", "side_with_seller", "partial"):
        raise ValidationError("Unknown outcome")
    if outcome == "partial" and (not amount_vnd or not 0 < int(amount_vnd) <= refund_amount(c)):
        raise ValidationError(f"Partial refunds must be between 1 and {refund_amount(c):,} ₫")
    d = DisputeDecision(case_id=c.id, decided_by=agent.id, reason_code=reason_code.strip(), outcome=outcome,
                        amount_vnd=int(amount_vnd) if amount_vnd else None, note=note, at=policy.now())
    db.session.add(d)
    db.session.flush()
    audit.record(agent, "dispute.decide", "return_case", c.id, f"{reason_code}: {outcome}")
    if outcome == "refund_customer":
        execute_refund(c, actor=agent)
    elif outcome == "partial":
        execute_refund(c, int(amount_vnd), actor=agent)
    else:
        _set_status(c, "closed", agent, f"Decision {reason_code}: seller upheld")
        _settle_order(c.order, agent)
    db.session.commit()
    return d
