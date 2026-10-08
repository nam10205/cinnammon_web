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
