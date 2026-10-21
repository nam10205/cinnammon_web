from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

from ..order.service import shipping_fee
from . import service

bp = Blueprint("cart", __name__)


def _int(name: str, default: int = 0) -> int:
    try:
        return int(request.form.get(name, default))
    except (TypeError, ValueError):
        return default


@bp.get("/cart")
def view():
    lines = service.lines()
    sub = sum(l.line_total for l in lines)
    fee = shipping_fee(sub) if lines else 0
    return render_template("customer/cart.html", lines=lines, subtotal=sub, fee=fee, total=sub + fee)


@bp.post("/cart/add")
def add():
    service.add(_int("product_id"), _int("qty", 1))
    return redirect(url_for("cart.view"))


@bp.post("/cart/update")
def update():
    service.set_qty(_int("product_id"), _int("qty"))
    return redirect(url_for("cart.view"))


@bp.post("/cart/remove")
def remove():
    service.remove(_int("product_id"))
    return redirect(url_for("cart.view"))
