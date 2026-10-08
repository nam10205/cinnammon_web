from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ..order import service as order_service
from . import service

bp = Blueprint("returns", __name__)


@bp.route("/orders/<int:order_id>/return", methods=["GET", "POST"])
@require_role("customer")
def new(order_id):
    u = current_user()
    o = order_service.get_for_customer(u, order_id)
    if request.method == "POST":
        f = request.form
        items = {}
        for it in o.items:
            raw = f.get(f"qty_{it.id}", "0") or "0"
            items[it.id] = int(raw) if raw.strip().lstrip("-").isdigit() else 0
        c = service.open_case(u, o.id, items, f.get("reason"), f.get("remedy"), f.get("statement"),
                              request.files.get("evidence"))
        flash("Return request submitted", "success")
        return redirect(url_for("returns.detail", case_id=c.id))
    return render_template("customer/return_form.html", o=o)


@bp.get("/returns/<int:case_id>")
@require_role("customer")
def detail(case_id):
    c = service.case_for_customer(current_user(), case_id)
    return render_template("customer/return_detail.html", c=c, can_escalate=service.can_escalate(c),
                           amount=service.refund_amount(c))


@bp.post("/returns/<int:case_id>/<action>")
@require_role("customer")
def customer_action(case_id, action):
    u = current_user()
    if action == "escalate":
        service.escalate(u, case_id, request.form.get("statement"))
        flash("Escalated to MarketplaceX dispute review", "warning")
    elif action == "accept-proposal":
        service.accept_proposal(u, case_id)
        flash("Refund issued", "success")
    elif action == "evidence":
        service.add_evidence(u, case_id, request.form.get("statement"), request.files.get("evidence"))
        flash("Evidence added", "success")
    return redirect(url_for("returns.detail", case_id=case_id))


@bp.get("/seller/returns")
@require_role("seller")
def seller_list():
    from ..seller.routes import current_shop
    shop = current_shop()
    return render_template("seller/returns.html", cases=service.cases_for_shop(shop.id) if shop else [])


@bp.get("/seller/returns/<int:case_id>")
@require_role("seller")
def seller_detail(case_id):
    c = service.case_for_seller(current_user(), case_id)
    return render_template("seller/return_detail.html", c=c, amount=service.refund_amount(c))


@bp.post("/seller/returns/<int:case_id>/<action>")
@require_role("seller")
def seller_action(case_id, action):
    u = current_user()
    f = request.form
    if action == "respond":
        service.seller_respond(u, case_id, f.get("decision"), f.get("reason"), f.get("amount_vnd", type=int))
    elif action == "inspect":
        service.inspect(u, case_id, f.get("passed") == "1", f.get("note"))
    elif action == "evidence":
        service.add_evidence(u, case_id, f.get("statement"), request.files.get("evidence"))
    flash("Case updated", "success")
    return redirect(url_for("returns.seller_detail", case_id=case_id))
