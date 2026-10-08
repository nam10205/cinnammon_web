"""Operational dashboard metrics (report §4.5). Reads data; never writes transactional tables."""
from __future__ import annotations

from collections import Counter, defaultdict

from ...extensions import db
from ..admin import policy


def orders_by_status() -> dict:
    from ..order.models import Order
    return dict(Counter(o.status for o in Order.query.all()))


def avg_paid_to_packed_hours():
    from ..order.models import OrderStatusHistory
    times = defaultdict(dict)
    for h in OrderStatusHistory.query.filter(OrderStatusHistory.to_status.in_(["Confirmed", "ReadyToShip"])).all():
        times[h.order_id][h.to_status] = h.at
    spans = [(t["ReadyToShip"] - t["Confirmed"]).total_seconds() / 3600 for t in times.values()
             if "Confirmed" in t and "ReadyToShip" in t]
    return round(sum(spans) / len(spans), 2) if spans else None


def cancellations_by_actor() -> dict:
    from ..order.models import OrderStatusHistory
    out = Counter()
    for h in OrderStatusHistory.query.filter_by(to_status="Cancelled").all():
        out[h.actor.role if h.actor else "system"] += 1
    return dict(out)


def refund_aging() -> list[dict]:
    from ..returns.service import open_cases
    now = policy.now()
    return [{"case_id": c.id, "age_hours": round((now - c.created_at).total_seconds() / 3600, 1), "status": c.status}
            for c in open_cases()]


def payment_mismatches() -> list[str]:
    from ..order.models import Order
    from ..payment.models import PaymentAttempt
    issues = []
    confirmed = {"Confirmed", "Preparing", "ReadyToShip", "Shipped", "Delivered", "Completed", "ReturnRequested",
                 "Returned", "Rejected", "Refunded", "CancelRequested", "DeliveryException", "Disputed", "Cancelled"}
    for p in PaymentAttempt.query.filter_by(status="captured").all():
        if not Order.query.filter(Order.group_id == p.group_id, Order.status.in_(confirmed)).first():
            issues.append(f"Payment {p.provider_ref} captured without a confirmed order")
    for o in Order.query.filter(Order.status.in_(confirmed - {"Cancelled"})).all():
        if not PaymentAttempt.query.filter_by(group_id=o.group_id, status="captured").first():
            issues.append(f"Order #{o.id} is {o.status} without a captured payment")
    return issues


def zero_result_rate() -> float:
    from ..search.models import SearchTrace
    total = SearchTrace.query.count()
    return round(SearchTrace.query.filter_by(result_count=0).count() / total, 3) if total else 0.0


def notification_failure_rate() -> float:
    from ..notification.models import Notification
    total = Notification.query.count()
    return round(Notification.query.filter_by(status="failed").count() / total, 3) if total else 0.0


def inventory_oversell() -> int:
    from ..order.models import OrderStatusHistory
    return sum(1 for h in OrderStatusHistory.query.filter_by(to_status="Cancelled").all()
               if h.actor and h.actor.role == "seller" and "stock" in (h.reason or "").lower())


def event_backlog() -> dict:
    from ...events import EventLog
    return dict(Counter(e.name for e in EventLog.query.all()))


def summary() -> dict:
    return {"orders_by_status": orders_by_status(), "paid_to_packed_h": avg_paid_to_packed_hours(),
            "cancellations": cancellations_by_actor(), "refund_aging": refund_aging(),
            "payment_mismatches": payment_mismatches(), "zero_result_rate": zero_result_rate(),
            "notification_failure_rate": notification_failure_rate(), "oversell": inventory_oversell(),
            "events": event_backlog(), "clock_offset_h": policy.clock_offset_hours()}
