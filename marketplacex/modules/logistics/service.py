"""Logistics: shipping quotes, shipments, tracking timeline (FR14)."""
from __future__ import annotations

from datetime import timedelta

from ...adapters.logistics_provider import carrier
from ...extensions import db
from ..seller.models import Shop
from .models import Shipment, TrackingEvent


def quote(address, shop_ids: list[int]) -> dict[int, int]:
    out = {}
    for sid in shop_ids:
        shop = db.session.get(Shop, sid)
        out[sid] = carrier.quote(shop.location if shop else "", address.city if address else "")
    return out


def has_delivery_event(order_id: int) -> bool:
    return (TrackingEvent.query.join(Shipment)
            .filter(Shipment.order_id == order_id, Shipment.kind == "forward", TrackingEvent.status == "delivered")
            .first() is not None)


def get_shipment(shipment_id: int) -> Shipment:
    s = db.session.get(Shipment, shipment_id)
    if s is None:
        from ...errors import NotFound
        raise NotFound("Shipment not found")
    return s


def shipments_of(order) -> list[Shipment]:
    return Shipment.query.filter_by(order_id=order.id).order_by(Shipment.id).all()


def create_shipment(order, weight_g: int, kind: str = "forward", return_case=None) -> Shipment:
    from ...errors import ValidationError
    from ..admin import policy
    if kind == "forward" and Shipment.query.filter_by(order_id=order.id, kind="forward").first():
        raise ValidationError("This order already has an active shipment")
    if int(weight_g or 0) < 0:
        raise ValidationError("Weight cannot be negative")
    tracking, label = carrier.create(order.id, kind)
    s = Shipment(order_id=order.id, kind=kind, return_case_id=getattr(return_case, "id", None), tracking_no=tracking,
                 label_url=label, weight_g=int(weight_g or 0), status="label_created", created_at=policy.now(),
                 promised_pickup_at=policy.now() + timedelta(hours=24))
    db.session.add(s)
    db.session.commit()
    return s


def _location(s: Shipment, status: str) -> str:
    shop_city = s.order.shop.location
    cust_city = s.order.address_snapshot.get("city", "")
    origin, dest = (shop_city, cust_city) if s.kind == "forward" else (cust_city, shop_city)
    return {"picked_up": origin, "in_transit": "Sorting hub", "out_for_delivery": dest,
            "delivered": dest, "delivery_failed": dest}.get(status, "")


def _append(s: Shipment, status: str) -> TrackingEvent:
    from ...events import publish
    from ..admin import policy
    seq = (s.events[-1].seq + 1) if s.events else 1
    ev = TrackingEvent(shipment_id=s.id, seq=seq, status=status, location=_location(s, status), at=policy.now())
    db.session.add(ev)
    s.events.append(ev)
    s.status = status
    db.session.flush()
    publish("TrackingChanged", s.id, {"shipment_id": s.id, "order_id": s.order_id, "kind": s.kind, "status": status,
                                      "return_case_id": s.return_case_id})
    db.session.commit()
    return ev


def record_pickup(s: Shipment) -> TrackingEvent:
    return _append(s, "picked_up")


def advance(s: Shipment, fail: bool = False) -> TrackingEvent:
    """Carrier simulator: next tracking event. Forward delivery records proof of delivery."""
    from ...errors import IllegalTransition
    from ..order import service as order_service
    order = s.order
    if s.status == "delivered":
        raise IllegalTransition("Shipment already delivered")
    if s.kind == "forward" and order.status != "Shipped":
        raise IllegalTransition("Carrier does not have custody of this order")
    done = [e.status for e in s.events if e.status in carrier.NEXT]
    nxt = "delivery_failed" if fail else carrier.NEXT[min(len(set(done)), len(carrier.NEXT) - 1)]
    ev = _append(s, nxt)
    if s.kind == "forward":
        if nxt == "delivered":
            order_service.transition(order, "Delivered", None, "Carrier proof of delivery")
        elif nxt == "delivery_failed":
            order_service.transition(order, "DeliveryException", None, "Carrier could not deliver")
    return ev


def reattempt(actor, s: Shipment) -> object:
    from ..order import service as order_service
    order = s.order
    order_service.transition(order, "Shipped", actor, "Delivery re-attempt scheduled")
    _append(s, "in_transit")
    return order


def pickup_overdue(s: Shipment) -> bool:
    from ..admin import policy
    picked = any(e.status == "picked_up" for e in s.events)
    return (not picked and s.promised_pickup_at is not None and policy.now() > s.promised_pickup_at
            and s.order.status == "ReadyToShip")
