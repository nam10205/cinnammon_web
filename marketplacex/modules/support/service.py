"""Support console: case history with masked personal data and protected actions (FR28, report §11.1)."""
from __future__ import annotations

from ...errors import IllegalTransition, NotEligible, NotFound, ValidationError
from ...extensions import db
from ..admin import policy
from ..audit import service as audit
from ..identity.models import User
from ..order import service as order_service
from ..order.models import Order
from .models import CaseNote, SupportCase


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}"


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "—"
    return "*" * (len(phone) - 4) + phone[-4:]


def _reason(reason: str) -> str:
    if not (reason or "").strip():
        raise ValidationError("A reason is required")
    return reason.strip()


def open_case(customer, order_id: int | None, subject: str, body: str) -> SupportCase:
    if order_id:
        order_service.get_for_customer(customer, order_id)
    if not (body or "").strip():
        raise ValidationError("Please describe your question")
    c = SupportCase(customer_id=customer.id, order_id=order_id, subject=(subject or body)[:200], status="open",
                    created_at=policy.now())
    db.session.add(c)
    db.session.flush()
    db.session.add(CaseNote(case_id=c.id, author_id=customer.id, body=body.strip(), at=policy.now()))
    db.session.commit()
    return c


def get_case(case_id: int) -> SupportCase:
    c = db.session.get(SupportCase, case_id)
    if c is None:
        raise NotFound("Case not found")
    return c


def search(agent, q: str) -> dict:
    q = (q or "").strip()
    out = {"customers": [], "orders": [], "cases": []}
    if not q:
        out["cases"] = SupportCase.query.filter(SupportCase.status != "resolved").order_by(SupportCase.id.desc()).all()
        return out
    like = f"%{q.lower()}%"
    out["customers"] = User.query.filter(User.role == "customer", db.or_(db.func.lower(User.email).like(like),
                                                                           db.func.lower(User.name).like(like))).all()
    if q.lstrip("#").isdigit():
        n = int(q.lstrip("#"))
        o = db.session.get(Order, n)
        out["orders"] = [o] if o else []
        c = db.session.get(SupportCase, n)
        out["cases"] = [c] if c else []
    ids = [u.id for u in out["customers"]]
    if ids:
        out["orders"] += Order.query.filter(Order.customer_id.in_(ids)).order_by(Order.id.desc()).all()
        out["cases"] += SupportCase.query.filter(SupportCase.customer_id.in_(ids)).order_by(SupportCase.id.desc()).all()
    audit.record(agent, "support.search", "query", q[:60])
    db.session.commit()
    return out


def reveal(agent, user_id: int, field: str, reason: str) -> str:
    reason = _reason(reason)
    u = db.session.get(User, user_id)
    if u is None or field not in ("email", "phone"):
        raise NotFound("Not found")
    audit.record(agent, "pii.reveal", "user", u.id, f"{field}: {reason}")
    db.session.commit()
    return getattr(u, field) or ""


def add_note(agent, case_id: int, body: str) -> CaseNote:
    c = get_case(case_id)
    if not (body or "").strip():
        raise ValidationError("Note cannot be empty")
    n = CaseNote(case_id=c.id, author_id=agent.id, body=body.strip(), at=policy.now())
    db.session.add(n)
    if c.status == "open":
        c.status = "pending"
    db.session.commit()
    return n


def set_status(agent, case_id: int, status: str, reason: str) -> SupportCase:
    reason = _reason(reason)
    if status not in ("open", "pending", "resolved"):
        raise ValidationError("Unknown status")
    c = get_case(case_id)
    before = c.status
    c.status = status
    audit.record(agent, "case.status", "support_case", c.id, reason, {"status": before}, {"status": status})
    db.session.commit()
    return c


def assign(agent, case_id: int) -> SupportCase:
    c = get_case(case_id)
    c.assignee_id = agent.id
    audit.record(agent, "case.assign", "support_case", c.id)
    db.session.commit()
    return c


def timeline(agent, case_id: int) -> list[dict]:
    """Single chronological case view (report persona: support agent)."""
    c = get_case(case_id)
    items = [{"at": n.at, "who": n.author.name, "kind": "note", "text": n.body} for n in c.notes]
    if c.order_id:
        o = c.order
        items += [{"at": h.at, "who": h.actor.name if h.actor else "System", "kind": "order",
                   "text": f"Order #{o.id} → {h.to_status}" + (f" ({h.reason})" if h.reason else "")} for h in o.history]
        from ..returns.service import cases_for_order
        for rc in cases_for_order(o.id):
            items += [{"at": e.at, "who": e.author.name if e.author else "System", "kind": "return",
                       "text": f"Return #{rc.id}: {e.content}"} for e in rc.evidence]
    audit.record(agent, "case.view", "support_case", c.id)
    db.session.commit()
    return sorted(items, key=lambda x: x["at"])


def disputes() -> list:
    from ..returns.models import ReturnCase
    return ReturnCase.query.filter_by(status="disputed").order_by(ReturnCase.id).all()


def disputed_orders() -> list[Order]:
    return Order.query.filter_by(status="Disputed").order_by(Order.id).all()


def report_not_received(customer, order_id: int, statement: str) -> SupportCase:
    o = order_service.get_for_customer(customer, order_id)
    if o.status != "Delivered":
        raise NotEligible("Only delivered orders can be reported as not received")
    order_service.transition(o, "Disputed", customer, f"Customer reports item not received: {statement}")
    return open_case(customer, o.id, "Item not received", statement or "Item not received")


def resolve_order_dispute(agent, order_id: int, refund: bool, reason_code: str) -> Order:
    from ..payment import service as payment
    reason_code = _reason(reason_code)
    o = order_service.get_order(order_id)
    if o.status != "Disputed":
        raise IllegalTransition("Order is not under dispute")
    if refund:
        p = payment.captured_for_group(o.group_id)
        amount = min(o.total_vnd, payment.refundable_vnd(p.id))
        payment.refund(p.id, amount, f"dispute-order-{o.id}", order_id=o.id)
        order_service.transition(o, "Refunded", agent, f"Dispute decision {reason_code}: refund")
    else:
        order_service.transition(o, "Completed", agent, f"Dispute decision {reason_code}: delivery upheld")
    for c in SupportCase.query.filter_by(order_id=o.id).all():
        c.status = "resolved"
    db.session.commit()
    return o
