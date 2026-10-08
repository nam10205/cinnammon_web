"""Notifications driven by domain events (FR20). Delivery result is recorded per channel."""
from __future__ import annotations

from flask import current_app

from ...adapters.notification_provider import FakeNotificationProvider
from ...errors import NotFound
from ...events import subscribe
from ...extensions import db
from ..admin import policy
from .models import Notification

STATUS_TEXT = {
    "PendingPayment": "is waiting for payment", "Confirmed": "is confirmed", "Preparing": "is being prepared by the seller",
    "ReadyToShip": "is packed and waiting for the carrier", "Shipped": "has been shipped", "Delivered": "was delivered",
    "Completed": "is completed", "Cancelled": "was cancelled", "PaymentFailed": "payment failed",
    "CancelRequested": "has a cancellation request", "ReturnRequested": "has a return request",
    "Refunded": "was refunded", "Returned": "was returned", "Rejected": "return was rejected",
    "DeliveryException": "has a delivery problem", "Disputed": "is under dispute",
}


def notify(user_id: int, template: str, body: str, channel: str = "in_app", link: str | None = None) -> Notification:
    from ..identity.models import User
    u = db.session.get(User, user_id)
    ok = FakeNotificationProvider(current_app.config.get("NOTIFICATION_FAILURE_RATE", 0)).send(
        channel, getattr(u, "email", ""), body)
    n = Notification(user_id=user_id, channel=channel, template=template, body=body, link=link,
                     status="sent" if ok else "failed", created_at=policy.now())
    db.session.add(n)
    db.session.flush()
    return n


def _both(user_id: int, template: str, body: str, link: str | None):
    notify(user_id, template, body, "in_app", link)
    notify(user_id, template, body, "email", link)


def unread_count(user) -> int:
    return Notification.query.filter_by(user_id=user.id, channel="in_app", read_at=None).count()


def inbox(user) -> list[Notification]:
    return (Notification.query.filter_by(user_id=user.id, channel="in_app")
            .order_by(Notification.id.desc()).limit(100).all())


def mark_read(user, notification_id: int) -> None:
    n = db.session.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise NotFound("Notification not found")
    n.read_at = policy.now()
    db.session.commit()


def mark_all_read(user) -> None:
    for n in Notification.query.filter_by(user_id=user.id, read_at=None).all():
        n.read_at = policy.now()
    db.session.commit()


def _shop_owner(shop_id: int) -> int:
    from ..seller.models import Shop
    return db.session.get(Shop, shop_id).owner_id


@subscribe("OrderCreated", "notification")
def _on_order_created(event) -> None:
    p = event.payload
    _both(p["customer_id"], "order_created", f"Order #{p['order_id']} placed successfully.", f"/orders/{p['order_id']}")
    notify(_shop_owner(p["shop_id"]), "new_order", f"New order #{p['order_id']} is waiting for acceptance.",
           link=f"/seller/orders/{p['order_id']}")


@subscribe("OrderStatusChanged", "notification")
def _on_status(event) -> None:
    p = event.payload
    if p["to"] in ("Draft", "PendingPayment"):
        return
    _both(p["customer_id"], "order_status", f"Order #{p['order_id']} {STATUS_TEXT.get(p['to'], p['to'])}.",
          f"/orders/{p['order_id']}")
    if p["to"] in ("CancelRequested", "ReturnRequested", "Disputed"):
        notify(_shop_owner(p["shop_id"]), "order_status", f"Order #{p['order_id']} {STATUS_TEXT[p['to']]}.",
               link=f"/seller/orders/{p['order_id']}")
