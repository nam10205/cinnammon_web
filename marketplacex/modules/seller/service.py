from __future__ import annotations

from ...errors import NotFound, ValidationError
from ...extensions import db
from .models import Shop


def create_shop(owner, name: str, location: str, description: str = "") -> Shop:
    if not (name or "").strip() or not (location or "").strip():
        raise ValidationError("Shop name and location are required")
    if Shop.query.filter_by(name=name.strip()).first():
        raise ValidationError("Shop name already taken")
    s = Shop(owner_id=owner.id, name=name.strip(), location=location.strip(), description=description)
    db.session.add(s)
    db.session.commit()
    return s


def shops_of(user) -> list[Shop]:
    return Shop.query.filter_by(owner_id=user.id).order_by(Shop.id).all()


def get_shop(shop_id: int) -> Shop:
    s = db.session.get(Shop, shop_id)
    if s is None:
        raise NotFound("Shop not found")
    return s


def owned_shop(user, shop_id: int) -> Shop:
    s = db.session.get(Shop, shop_id)
    if s is None or s.owner_id != user.id:
        raise NotFound("Shop not found")
    return s


# --- Fulfilment (UC04, FR24) ---------------------------------------------------------------------

def _order(seller, order_id):
    from ..order import service as order_service
    return order_service.get_for_shop_owner(seller, order_id)


def accept(seller, order_id: int):
    from ..order import service as order_service
    return order_service.transition(_order(seller, order_id), "Preparing", seller, "Seller accepted the order")


def pack(seller, order_id: int, weight_g: int):
    from ..logistics import service as logistics
    from ..order import service as order_service
    o = _order(seller, order_id)
    if o.status != "Preparing":
        from ...errors import IllegalTransition
        raise IllegalTransition("Only orders being prepared can be packed")
    if not weight_g or int(weight_g) <= 0:
        raise ValidationError("Package weight is required")
    s = logistics.create_shipment(o, int(weight_g))
    order_service.transition(o, "ReadyToShip", seller, f"Packed, {int(weight_g)} g, label {s.tracking_no}")
    return s


def hand_over(seller, order_id: int):
    from ..logistics import service as logistics
    from ..order import service as order_service
    o = _order(seller, order_id)
    order_service.transition(o, "Shipped", seller, "Handed over to carrier")
    s = next(s for s in logistics.shipments_of(o) if s.kind == "forward")
    logistics.record_pickup(s)
    return o


def reject(seller, order_id: int, reason: str):
    from ...errors import IllegalTransition
    from ..order import service as order_service
    if not (reason or "").strip():
        raise ValidationError("A reason is required to reject an order")
    o = _order(seller, order_id)
    if o.status not in ("Confirmed", "DeliveryException"):
        raise IllegalTransition(f"Orders in status {o.status} cannot be rejected")
    order_service.transition(o, "Cancelled", seller, reason.strip())
    order_service.compensate_order(o, "Confirmed")
    return o


def resolve_cancel(seller, order_id: int, approve: bool, reason: str):
    from ..order import service as order_service
    return order_service.resolve_cancel(seller, _order(seller, order_id), approve, reason)
