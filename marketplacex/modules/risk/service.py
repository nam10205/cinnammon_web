"""Risk rules, alerts and hold/release decisions (FR29, report §11)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func

from ...errors import NotEligible, NotFound, ValidationError
from ...events import publish
from ...extensions import db
from ..admin import policy
from ..audit import service as audit
from .models import RiskAlert

HOLD_MINUTES = 24 * 60


def _raise_alert(target_type: str, target_id: int, customer, rule: str, score: float, context: dict) -> RiskAlert:
    a = RiskAlert(target_type=target_type, target_id=target_id, customer_id=getattr(customer, "id", None), rule=rule,
                  score=score, status="held", context=context, created_at=policy.now())
    db.session.add(a)
    db.session.flush()
    publish("RiskDecisionMade", a.id, {"alert_id": a.id, "target_type": target_type, "target_id": target_id,
                                       "rule": rule, "decision": "held"})
    db.session.commit()
    return a


def evaluate_checkout(customer, group) -> str:
    from ..promotion.models import Redemption
    total = group.total_vnd
    since = policy.now() - timedelta(hours=24)
    vouchers_today = Redemption.query.filter(Redemption.customer_id == customer.id, Redemption.status == "committed",
                                             Redemption.created_at >= since).count()
    rule = None
    if total > policy.get_int("risk_max_order_vnd"):
        rule, score = "HIGH_VALUE", min(1.0, total / (2 * policy.get_int("risk_max_order_vnd")))
    elif vouchers_today >= policy.get_int("risk_max_vouchers_per_day") and group.quote_payload.get("applied"):
        rule, score = "VOUCHER_VELOCITY", 0.7
    elif customer.created_at and customer.created_at > policy.now() - timedelta(hours=24) and total > 5_000_000:
        rule, score = "NEW_ACCOUNT_HIGH_VALUE", 0.8
    if rule is None:
        return "approved"
    from ..inventory import service as inventory
    from ..promotion import service as promo
    # Keep holds alive while an analyst reviews (otherwise the reservation sweep would cancel the checkout).
    inventory.extend_hold(group.attempt_id, HOLD_MINUTES)
    promo.extend_hold(group.attempt_id, HOLD_MINUTES)
    _raise_alert("checkout", group.id, customer, rule, round(score, 2),
                 {"total_vnd": total, "vouchers_today": vouchers_today, "account_created": str(customer.created_at)})
    return "held"


def _refunds_last_30d(customer_id: int) -> int:
    from ..checkout.models import CheckoutGroup
    from ..payment.models import PaymentAttempt, Refund
    since = policy.now() - timedelta(days=30)
    return (Refund.query.join(PaymentAttempt, Refund.payment_id == PaymentAttempt.id)
            .join(CheckoutGroup, CheckoutGroup.id == PaymentAttempt.group_id)
            .filter(CheckoutGroup.customer_id == customer_id, Refund.status == "succeeded",
                    Refund.created_at >= since).count())


def evaluate_refund(customer, case, amount_vnd: int) -> str:
    n = _refunds_last_30d(customer.id)
    if n >= policy.get_int("risk_max_refunds_30d"):
        _raise_alert("refund", case.id, customer, "REFUND_VELOCITY", 0.6, {"refunds_30d": n, "amount_vnd": amount_vnd})
        return "held"
    return "approved"


def get_alert(alert_id: int) -> RiskAlert:
    a = db.session.get(RiskAlert, alert_id)
    if a is None:
        raise NotFound("Alert not found")
    return a


def _decide(analyst, alert_id: int, status: str, reason: str) -> RiskAlert:
    if not (reason or "").strip():
        raise ValidationError("A reason is required")
    a = get_alert(alert_id)
    if a.status not in ("open", "held"):
        raise NotEligible("This alert has already been decided")
    a.status, a.decided_by, a.reason = status, analyst.id, reason.strip()
    audit.record(analyst, f"risk.{status}", "risk_alert", a.id, reason, {"status": "held"}, {"status": status})
    publish("RiskDecisionMade", a.id, {"alert_id": a.id, "target_type": a.target_type, "target_id": a.target_id,
                                       "rule": a.rule, "decision": status})
    db.session.commit()
    return a


def release(analyst, alert_id: int, reason: str) -> RiskAlert:
    a = get_alert(alert_id)
    if a.target_type == "checkout":
        from ..checkout import service as checkout
        from ..checkout.models import CheckoutGroup
        g = db.session.get(CheckoutGroup, a.target_id)
        if g is None or g.status != "placing":
            raise NotEligible("This checkout is no longer waiting (it expired or was cancelled)")
        _decide(analyst, alert_id, "released", reason)
        checkout.continue_after_risk(g)
        from ..notification import service as notif
        notif.notify(g.customer_id, "risk_released", "Your order passed review. Please complete payment.",
                     link=f"/checkout/{g.id}/result")
        db.session.commit()
    elif a.target_type == "refund":
        from ..returns import service as returns
        case = returns.get_case(a.target_id)
        _decide(analyst, alert_id, "released", reason)
        returns.execute_refund(case, case.pending_amount_vnd, actor=analyst, skip_risk=True)
    else:
        _decide(analyst, alert_id, "dismissed", reason)
    return a


def reject(analyst, alert_id: int, reason: str) -> RiskAlert:
    a = get_alert(alert_id)
    _decide(analyst, alert_id, "rejected", reason)
    if a.target_type == "checkout":
        from ..checkout import service as checkout
        from ..checkout.models import CheckoutGroup
        g = db.session.get(CheckoutGroup, a.target_id)
        if g is not None:
            checkout.compensate(g, "Rejected by risk review")
    elif a.target_type == "refund":
        from ..returns import service as returns
        case = returns.get_case(a.target_id)
        returns.close_after_risk(case, analyst, reason)
    return a


def alerts(status: str | None = None) -> list[RiskAlert]:
    q = RiskAlert.query
    if status == "open":
        q = q.filter(RiskAlert.status.in_(["open", "held"]))
    elif status:
        q = q.filter_by(status=status)
    return q.order_by(RiskAlert.id.desc()).all()


def customer_history(customer_id: int) -> dict:
    from ..order.models import Order
    return {"orders": Order.query.filter_by(customer_id=customer_id).count(),
            "refunds_30d": _refunds_last_30d(customer_id),
            "alerts": RiskAlert.query.filter_by(customer_id=customer_id).count()}
