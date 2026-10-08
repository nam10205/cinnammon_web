from __future__ import annotations

import uuid

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ...errors import QuoteChanged, QuoteExpired
from ..cart import service as cart
from ..identity.service import default_address
from ..order import service as order_service
from ..payment import service as payment
from . import service

bp = Blueprint("checkout", __name__)


@bp.get("/checkout")
@require_role("customer")
def start():
    u = current_user()
    c = cart.get_cart(u)
    groups = cart.grouped(c)
    da = default_address(u)
    return render_template("customer/checkout.html", groups=groups, user=u,
                           default_address_id=da.id if da else None, vouchers=request.args.get("vouchers", ""))


@bp.post("/checkout/quote")
@require_role("customer")
def make_quote():
    codes = [c for c in (request.form.get("vouchers") or "").replace(";", ",").split(",")]
    g = service.quote(current_user(), request.form.get("address_id", type=int), codes)
    return redirect(url_for("checkout.review", group_id=g.id))


@bp.get("/checkout/<int:group_id>")
@require_role("customer")
def review(group_id):
    g = service.get_group(current_user(), group_id)
    if g.status != "quoted":
        return redirect(url_for("checkout.result", group_id=g.id))
    return render_template("customer/checkout_review.html", g=g, idempotency_key=uuid.uuid4().hex)


@bp.post("/checkout/<int:group_id>/place")
@require_role("customer")
def place(group_id):
    u = current_user()
    try:
        g = service.place_order(u, group_id, request.form.get("idempotency_key"), request.form.get("quote_hash"))
    except (QuoteChanged, QuoteExpired) as e:
        changed = getattr(e, "changed", [])
        details = "; ".join(f"{c['title']}: {c['change']}" for c in changed)
        flash(f"{e.message}. {details}".strip(), "warning")
        old = service.get_group(u, group_id)
        return redirect(url_for("checkout.start", vouchers=",".join(old.voucher_codes or [])))
    p = payment.latest_for_group(g.id)
    if g.status == "placing" and p is not None and p.status == "pending":
        return redirect(url_for("payment.pay_page", payment_id=p.id))
    return redirect(url_for("checkout.result", group_id=g.id))


@bp.get("/checkout/<int:group_id>/result")
@require_role("customer")
def result(group_id):
    g = service.get_group(current_user(), group_id)
    return render_template("customer/checkout_result.html", g=g, orders=order_service.orders_of_group(g.id),
                           payment=payment.latest_for_group(g.id))
