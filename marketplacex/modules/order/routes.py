from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from . import service

bp = Blueprint("order", __name__)


@bp.get("/orders")
@require_role("customer")
def my_orders():
    try:
        from ..checkout import service as checkout
        checkout.sweep()
    except ImportError:
        pass
    return render_template("customer/orders.html", orders=service.orders_of_customer(current_user()))


@bp.get("/orders/<int:order_id>")
@require_role("customer")
def detail(order_id):
    o = service.get_for_customer(current_user(), order_id)
    extras = {}
    try:
        from ..payment import service as payment
        extras["payment"] = payment.latest_for_group(o.group_id)
    except ImportError:
        pass
    try:
        from ..review.models import Review
        extras["reviewed"] = {r.order_item_id for r in Review.query.filter(
            Review.order_item_id.in_([i.id for i in o.items])).all()}
    except ImportError:
        extras["reviewed"] = set()
    try:
        from ..returns import service as returns
        extras["cases"] = returns.cases_for_order(o.id)
    except ImportError:
        extras["cases"] = []
    try:
        from ..checkout.models import CheckoutGroup
        from ...extensions import db
        extras["group"] = db.session.get(CheckoutGroup, o.group_id)
    except ImportError:
        pass
    return render_template("customer/order_detail.html", o=o, **extras)


@bp.post("/orders/<int:order_id>/cancel")
@require_role("customer")
def cancel(order_id):
    u = current_user()
    o = service.get_for_customer(u, order_id)
    service.request_cancel(u, o, request.form.get("reason"))
    flash("Cancellation requested" if o.status == "CancelRequested" else "Order cancelled", "success")
    return redirect(url_for("order.detail", order_id=o.id))
