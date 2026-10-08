from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ..audit import service as audit
from ..identity.models import User
from ..order import service as order_service
from ..returns import service as returns
from . import service

bp = Blueprint("support", __name__)


@bp.get("/support/")
@require_role("support")
def dashboard():
    q = request.args.get("q", "")
    return render_template("support/dashboard.html", q=q, results=service.search(current_user(), q),
                           disputes=service.disputes(), disputed_orders=service.disputed_orders(),
                           mask_email=service.mask_email)


@bp.get("/support/customers/<int:user_id>")
@require_role("support")
def customer(user_id):
    u = User.query.get_or_404(user_id)
    revealed = {}
    audit.record(current_user(), "customer.view", "user", u.id)
    from ...extensions import db
    db.session.commit()
    return render_template("support/customer.html", u=u, orders=order_service.orders_of_customer(u),
                           email=service.mask_email(u.email), phone=service.mask_phone(u.phone), revealed=revealed)


@bp.post("/support/customers/<int:user_id>/reveal")
@require_role("support")
def reveal(user_id):
    u = User.query.get_or_404(user_id)
    field = request.form.get("field")
    value = service.reveal(current_user(), u.id, field, request.form.get("reason"))
    return render_template("support/customer.html", u=u, orders=order_service.orders_of_customer(u),
                           email=service.mask_email(u.email), phone=service.mask_phone(u.phone), revealed={field: value})


@bp.get("/support/cases/<int:case_id>")
@require_role("support")
def case(case_id):
    c = service.get_case(case_id)
    return render_template("support/case.html", c=c, timeline=service.timeline(current_user(), c.id),
                           email=service.mask_email(c.customer.email))


@bp.post("/support/cases/<int:case_id>/<action>")
@require_role("support")
def case_action(case_id, action):
    u, f = current_user(), request.form
    if action == "note":
        service.add_note(u, case_id, f.get("body"))
    elif action == "status":
        service.set_status(u, case_id, f.get("status"), f.get("reason"))
    elif action == "assign":
        service.assign(u, case_id)
    flash("Case updated", "success")
    return redirect(url_for("support.case", case_id=case_id))


@bp.get("/support/disputes/<int:case_id>")
@require_role("support")
def dispute(case_id):
    c = returns.get_case(case_id)
    audit.record(current_user(), "dispute.view", "return_case", c.id)
    from ...extensions import db
    db.session.commit()
    return render_template("support/dispute.html", c=c, amount=returns.refund_amount(c))


@bp.post("/support/disputes/<int:case_id>/decide")
@require_role("support")
def decide(case_id):
    f = request.form
    returns.decide_dispute(current_user(), case_id, f.get("outcome"), f.get("reason_code"),
                           f.get("amount_vnd", type=int), f.get("note", ""))
    flash("Decision recorded", "success")
    return redirect(url_for("support.dispute", case_id=case_id))


@bp.post("/support/orders/<int:order_id>/resolve")
@require_role("support")
def resolve_order(order_id):
    service.resolve_order_dispute(current_user(), order_id, request.form.get("refund") == "1", request.form.get("reason_code"))
    flash("Order dispute resolved", "success")
    return redirect(url_for("support.dashboard"))


@bp.post("/orders/<int:order_id>/support")
@require_role("customer")
def open_from_order(order_id):
    service.open_case(current_user(), order_id, f"Question about order #{order_id}", request.form.get("body"))
    flash("Support case opened. An agent will reply soon.", "success")
    return redirect(url_for("order.detail", order_id=order_id))


@bp.post("/orders/<int:order_id>/not-received")
@require_role("customer")
def not_received(order_id):
    service.report_not_received(current_user(), order_id, request.form.get("statement"))
    flash("We've opened a dispute. Support will review it.", "warning")
    return redirect(url_for("order.detail", order_id=order_id))
