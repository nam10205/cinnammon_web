"""Session cart: state lives in flask.session["cart"] as {str(product_id): qty}."""
from __future__ import annotations

from dataclasses import dataclass

from flask import session

from ...errors import ValidationError
from ...extensions import db
from ..catalog.models import Product
from ..catalog import service as catalog


@dataclass
class CartLine:
    product: Product
    qty: int

    @property
    def line_total(self) -> int:
        return self.qty * self.product.price


def raw() -> dict[int, int]:
    data = session.get("cart")
    out: dict[int, int] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            try:
                pid, qty = int(k), int(v)
            except (TypeError, ValueError):
                continue
            if qty > 0:
                out[pid] = qty
    return out


def _save(cart: dict[int, int]) -> None:
    session["cart"] = {str(k): v for k, v in cart.items() if v > 0}


def lines() -> list[CartLine]:
    out = []
    for pid, qty in raw().items():
        p = db.session.get(Product, pid)
        if p is None:
            continue
        qty = min(qty, p.stock_quantity)
        if qty > 0:
            out.append(CartLine(p, qty))
    return out


def subtotal() -> int:
    return sum(line.line_total for line in lines())


def add(product_id: int, qty: int = 1) -> None:
    p = catalog.get_product(product_id)
    if p.stock_quantity <= 0:
        raise ValidationError(f"{p.title} is out of stock")
    cart = raw()
    cart[p.id] = min(cart.get(p.id, 0) + max(1, qty), p.stock_quantity)
    _save(cart)


def set_qty(product_id: int, qty: int) -> None:
    cart = raw()
    if qty <= 0:
        cart.pop(product_id, None)
    else:
        p = db.session.get(Product, product_id)
        if p is None:
            cart.pop(product_id, None)
        else:
            cart[product_id] = min(qty, p.stock_quantity)
    _save(cart)


def remove(product_id: int) -> None:
    cart = raw()
    cart.pop(product_id, None)
    _save(cart)


def clear() -> None:
    session.pop("cart", None)
