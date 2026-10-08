"""Order lifecycle from report §9.5. No transition may bypass commercial controls."""
from __future__ import annotations

from datetime import timedelta
from typing import Callable

from ..admin import policy

TRANSITIONS: dict[str, set] = {
    "Draft": {"PendingPayment", "Cancelled"},
    "PendingPayment": {"Confirmed", "PaymentFailed", "Cancelled"},
    "Confirmed": {"Preparing", "Cancelled"},
    "Preparing": {"ReadyToShip", "CancelRequested"},
    "ReadyToShip": {"Shipped", "CancelRequested"},
    "Shipped": {"Delivered", "DeliveryException", "ReturnRequested"},
    "Delivered": {"Completed", "ReturnRequested", "Disputed"},
    "Completed": {"ReturnRequested"},
    "ReturnRequested": {"Returned", "Rejected", "Refunded"},
    "CancelRequested": {"Cancelled", "Preparing", "ReadyToShip"},
    "DeliveryException": {"Shipped", "Cancelled"},
    "Disputed": {"Refunded", "Completed"},
    "Cancelled": set(), "PaymentFailed": set(), "Refunded": set(), "Returned": set(), "Rejected": set(),
}
TERMINAL = {s for s, nxt in TRANSITIONS.items() if not nxt}


def _is_captured(group_id: int) -> bool:
    from ..payment import service as payment
    return payment.is_captured(group_id)


def _has_delivery(order_id: int) -> bool:
    from ..logistics import service as logistics
    return logistics.has_delivery_event(order_id)


def _payment_authorized(o) -> tuple[bool, str]:
    return _is_captured(o.group_id), "paymentAuthorized"


def _before_handover(o) -> tuple[bool, str]:
    return o.status == "ReadyToShip", "beforeHandover"


def _delivery_evidence(o) -> tuple[bool, str]:
    return _has_delivery(o.id), "deliveryEvidenceValid"


def _within_return_window(o) -> tuple[bool, str]:
    if o.delivered_at is None:
        return True, "withinReturnWindow"  # Shipped -> ReturnRequested (refused delivery)
    limit = o.delivered_at + timedelta(days=policy.get_int("return_window_days"))
    return policy.now() <= limit, "withinReturnWindow"


def _back_to_previous(o) -> tuple[bool, str]:
    return True, "cancelFrom"


GUARDS: dict[tuple, Callable] = {
    ("PendingPayment", "Confirmed"): _payment_authorized,
    ("ReadyToShip", "Shipped"): _before_handover,
    ("Shipped", "Delivered"): _delivery_evidence,
    ("Delivered", "ReturnRequested"): _within_return_window,
    ("Completed", "ReturnRequested"): _within_return_window,
}


def check(o, to: str) -> tuple[bool, str]:
    if to not in TRANSITIONS.get(o.status, set()):
        return False, f"{o.status} → {to} is not an approved transition"
    if o.status == "CancelRequested" and to != "Cancelled" and to != o.cancel_from:
        return False, f"cancelFrom: can only return to {o.cancel_from}"
    guard = GUARDS.get((o.status, to))
    if guard:
        ok, name = guard(o)
        if not ok:
            return False, f"Guard [{name}] failed for {o.status} → {to}"
    return True, ""
