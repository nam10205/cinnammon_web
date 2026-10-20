"""Cart grouped by shop; every change bumps the version (FR07). Saved items and recent searches (FR08)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ...errors import NotFound, PurchaseLimitExceeded, StaleVersion, ValidationError
from ...events import publish
from ...extensions import db
from ..admin import policy
from ..catalog import service as catalog
from ..search.models import SearchHistory
from .models import Cart, CartItem, SavedItem


@dataclass
class ShopGroup:
    shop: object
    items: list = field(default_factory=list)
    subtotal_vnd: int = 0


def get_cart(customer) -> Cart:
    c = Cart.query.filter_by(customer_id=customer.id).first()
    if c is None:
        c = Cart(customer_id=customer.id, version=1)
        db.session.add(c)
        db.session.commit()
    return c


def parse_qty(raw) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValidationError("Quantity must be a whole number")


def _bump(c: Cart) -> Cart:
    c.version += 1
    publish("CartChanged", c.id, {"cart_id": c.id, "version": c.version})
    db.session.commit()
    return c


def _item(c: Cart, offer_id: int) -> CartItem | None:
    return next((i for i in c.items if i.offer_id == offer_id), None)


def change_item(customer, offer_id: int, qty: int, expected_version: int | None = None) -> Cart:
    c = get_cart(customer)
    if expected_version is not None and int(expected_version) != c.version:
        raise StaleVersion()
    qty = int(qty)
    if qty < 0:
        raise ValidationError("Quantity cannot be negative")
    item = _item(c, offer_id)
    if qty == 0:
        if item is not None:
            c.items.remove(item)
        return _bump(c)
    o = catalog.get_offer(offer_id)
    if o.product.status != "active":
        raise ValidationError("This product is not available")
    if qty > o.purchase_limit:
        raise PurchaseLimitExceeded(f"You can buy at most {o.purchase_limit} of {o.product.title}")
    if item is None:
        c.items.append(CartItem(offer_id=offer_id, qty=qty, selected=True))
    else:
        item.qty = qty
    return _bump(c)


def add_item(customer, offer_id: int, qty: int = 1) -> Cart:
    if int(qty) <= 0:
        raise ValidationError("Quantity must be at least 1")
    item = _item(get_cart(customer), offer_id)
    return change_item(customer, offer_id, (item.qty if item else 0) + int(qty))


def set_selected(customer, offer_id: int, selected: bool) -> Cart:
    c = get_cart(customer)
    item = _item(c, offer_id)
    if item is None:
        raise NotFound("Item not in cart")
    item.selected = bool(selected)
    return _bump(c)


def grouped(cart: Cart) -> list[ShopGroup]:
    groups: dict[int, ShopGroup] = {}
    for i in cart.items:
        g = groups.setdefault(i.offer.shop_id, ShopGroup(shop=i.offer.shop))
        g.items.append(i)
        if i.selected:
            g.subtotal_vnd += i.offer.price_vnd * i.qty
    return list(groups.values())


def selected_items(customer, version: int | None = None) -> list[CartItem]:
    c = get_cart(customer)
    if version is not None and int(version) != c.version:
        raise StaleVersion()
    return [i for i in c.items if i.selected]


def remove_items(customer, offer_ids: list[int]) -> None:
    c = get_cart(customer)
    ids = set(offer_ids)
    for i in [i for i in c.items if i.offer_id in ids]:
        c.items.remove(i)
    _bump(c)


def toggle_saved(customer, kind: str, target_id: int) -> bool:
    if kind not in ("product", "shop"):
        raise ValidationError("Unknown saved item type")
    s = SavedItem.query.filter_by(customer_id=customer.id, kind=kind, target_id=int(target_id)).first()
    if s:
        db.session.delete(s)
        db.session.commit()
        return False
    db.session.add(SavedItem(customer_id=customer.id, kind=kind, target_id=int(target_id)))
    db.session.commit()
    return True


def saved(customer) -> list[SavedItem]:
    return SavedItem.query.filter_by(customer_id=customer.id).order_by(SavedItem.id.desc()).all()


def record_search(account, text: str, search_type: str = "text") -> None:
    cust = getattr(account, "customer", None)
    text = (text or "").strip()[:255]
    if cust is None or not text:
        return
    SearchHistory.query.filter_by(customer_id=cust.id, keyword=text, search_type=search_type).delete()
    db.session.add(SearchHistory(customer_id=cust.id, keyword=text, search_type=search_type,
                                 searched_at=policy.now()))
    db.session.flush()
    extra = (SearchHistory.query.filter_by(customer_id=cust.id, search_type=search_type)
             .order_by(SearchHistory.searched_at.desc(), SearchHistory.id.desc()).offset(10).all())
    for r in extra:
        db.session.delete(r)
    db.session.commit()


def recent_searches(account) -> list[SearchHistory]:
    cust = getattr(account, "customer", None)
    if cust is None:
        return []
    return (SearchHistory.query.filter_by(customer_id=cust.id, search_type="text")
            .order_by(SearchHistory.searched_at.desc(), SearchHistory.id.desc()).all())


def delete_recent(account, history_id: int) -> None:
    cust = getattr(account, "customer", None)
    r = db.session.get(SearchHistory, history_id)
    if r is None or cust is None or r.customer_id != cust.id:
        raise NotFound("Search not found")
    db.session.delete(r)
    db.session.commit()
