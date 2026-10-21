from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ... import auth
from ...errors import DomainError
from ..cart import service as cart
from . import service

bp = Blueprint("order", __name__)


@bp.get("/checkout")
@auth.require_role("customer")
def checkout():
    lines = cart.lines()
    sub = sum(l.line_total for l in lines)
    fee = service.shipping_fee(sub) if lines else 0
    return render_template("customer/checkout.html", lines=lines, subtotal=sub, fee=fee,
                           total=sub + fee, address=auth.current_customer().address)


@bp.post("/checkout")
@auth.require_role("customer")
def place():
    try:
        service.checkout(auth.current_customer(), cart.raw(), request.form.get("payment_method", ""),
                         request.form.get("card_number"))
    except DomainError as e:
        flash(e.message, "danger")
        return redirect(url_for("order.checkout"))
    cart.clear()
    flash("Order placed. Thank you!", "success")
    if "order.my_orders" in current_app.view_functions:
        return redirect(url_for("order.my_orders"))
    return redirect("/")
