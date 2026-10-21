from __future__ import annotations

from flask import Blueprint, jsonify, current_app, flash, redirect, render_template, request, url_for

from ... import auth
from ...errors import DomainError, NotFound
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


def _own_order(order_id: int):
    o = service.get_order(order_id)
    if o.customer_id != auth.current_customer().id:
        raise NotFound("Order not found")
    return o


@bp.get("/orders")
@auth.require_role("customer")
def my_orders():
    return render_template("customer/orders.html",
                           groups=service.orders_for_customer(auth.current_customer()))


@bp.get("/orders/<int:order_id>")
@auth.require_role("customer")
def detail(order_id):
    service.advance_due()
    o = _own_order(order_id)
    return render_template("customer/order_detail.html", order=o, progress=service.progress(o))


@bp.get("/orders/<int:order_id>/progress")
@auth.require_role("customer")
def progress_json(order_id):
    service.advance_due()
    return jsonify(service.progress(_own_order(order_id)))


@bp.post("/orders/<int:order_id>/cancel")
@auth.require_role("customer")
def cancel(order_id):
    o = _own_order(order_id)
    try:
        service.cancel(o)
        flash("Order cancelled", "success")
    except DomainError as e:
        flash(e.message, "danger")
    return redirect(url_for("order.detail", order_id=order_id))
