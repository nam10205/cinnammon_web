"""Logistics: shipping quotes, shipments, tracking timeline (FR14)."""
from __future__ import annotations

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
