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


# --- Shop profile and offers (FR21, FR23) ---------------------------------------------------------

def update_shop(seller, shop_id: int, name: str, location: str, description: str = "") -> Shop:
    from ..audit import service as audit
    s = owned_shop(seller, shop_id)
    if not (name or "").strip() or not (location or "").strip():
        raise ValidationError("Shop name and location are required")
    other = Shop.query.filter(Shop.name == name.strip(), Shop.id != s.id).first()
    if other:
        raise ValidationError("Shop name already taken")
    s.name, s.location, s.description = name.strip(), location.strip(), description or ""
    audit.record(seller, "shop.update", "shop", s.id)
    db.session.commit()
    return s


def submit_verification(seller, shop_id: int, info: str) -> Shop:
    from ..audit import service as audit
    s = owned_shop(seller, shop_id)
    if not (info or "").strip():
        raise ValidationError("Verification information is required")
    s.verification_info = info.strip()
    s.verification_status = "pending"
    audit.record(seller, "shop.verification_submitted", "shop", s.id)
    db.session.commit()
    return s


def update_offer(seller, offer_id: int, price_vnd: int, original_price_vnd, stock: int, purchase_limit: int,
                 version: int):
    from ...errors import StaleVersion
    from ..audit import service as audit
    from ..catalog import service as catalog
    from ..catalog.models import Offer
    from ..inventory import service as inventory
    o = db.session.get(Offer, offer_id)
    if o is None or o.shop.owner_id != seller.id:
        raise NotFound("Offer not found")
    if version is not None and int(version) != o.version:
        raise StaleVersion()
    if int(price_vnd) <= 0 or int(stock) < 0 or int(purchase_limit) <= 0:
        raise ValidationError("Price and purchase limit must be positive; stock cannot be negative")
    if original_price_vnd not in (None, "") and int(original_price_vnd) < int(price_vnd):
        raise ValidationError("Original price cannot be below the selling price")
    before = {"price": o.price_vnd, "stock": inventory.in_stock(o.id), "limit": o.purchase_limit}
    o.price_vnd = int(price_vnd)
    o.original_price_vnd = int(original_price_vnd) if original_price_vnd not in (None, "") else None
    o.purchase_limit = int(purchase_limit)
    o.version += 1
    inventory.get_ledger(o.id).available = int(stock)
    catalog.sync_product(o.product)
    audit.record(seller, "offer.update", "offer", o.id, None, before,
                 {"price": o.price_vnd, "stock": int(stock), "limit": o.purchase_limit})
    db.session.commit()
    return o
