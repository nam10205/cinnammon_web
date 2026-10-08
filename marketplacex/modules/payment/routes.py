from __future__ import annotations

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ...errors import NotFound
from . import service

bp = Blueprint("payment", __name__)


@bp.post("/payments/callback")
def callback():
    p = service.handle_callback(request.get_json(force=True) or {}, request.headers.get("X-Signature", ""))
    return jsonify({"status": p.status})


def _owned_payment(payment_id: int):
    p = service.get_payment(payment_id)
    try:
        from ..checkout.models import CheckoutGroup
        from ...extensions import db
        g = db.session.get(CheckoutGroup, p.group_id)
        if g is None or g.customer_id != current_user().id:
            raise NotFound("Payment not found")
    except ImportError:
        pass
    return p


def _result_url(p):
    if "checkout.result" in current_app.view_functions:
        return url_for("checkout.result", group_id=p.group_id)
    return "/"


@bp.get("/payments/<int:payment_id>/pay")
@require_role("customer")
def pay_page(payment_id):
    return render_template("customer/pay.html", payment=_owned_payment(payment_id))


@bp.post("/payments/<int:payment_id>/simulate/<outcome>")
@require_role("customer")
def simulate(payment_id, outcome):
    p = _owned_payment(payment_id)
    body = service.simulate(p.id, "fail" if outcome == "fail" else "success")
    service.handle_callback(body["payload"], body["signature"])
    if outcome == "duplicate":
        service.handle_callback(body["payload"], body["signature"])
        flash("The provider sent the same callback twice; it was processed once.", "info")
    flash("Payment successful" if p.status == "captured" else "Payment failed", "success" if p.status == "captured" else "danger")
    return redirect(_result_url(p))
