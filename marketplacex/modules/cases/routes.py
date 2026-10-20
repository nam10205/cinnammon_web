from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ..audit import service as audit
from ..identity.models import User
from ..order import service as order_service
from ..returns import service as returns
from . import service

bp = Blueprint("cases", __name__)


@bp.get("/admin/cases/")
@require_role("admin")
def dashboard():
    q = request.args.get("q", "")
    return render_template("admin/cases/dashboard.html", q=q, results=service.search(current_user(), q),
                           disputes=service.disputes(), disputed_orders=service.disputed_orders())


@bp.get("/admin/cases/cases/<int:case_id>")
@require_role("admin")
def case(case_id):
    c = service.get_case(case_id)
    return render_template("admin/cases/case.html", c=c, timeline=service.timeline(current_user(), c.id))


@bp.post("/admin/cases/cases/<int:case_id>/<action>")
@require_role("admin")
def case_action(case_id, action):
    u, f = current_user(), request.form
    if action == "note":
        service.add_note(u, case_id, f.get("body"))
    elif action == "status":
        service.set_status(u, case_id, f.get("status"), f.get("reason"))
    elif action == "assign":
        service.assign(u, case_id)
    flash("Case updated", "success")
    return redirect(url_for("cases.case", case_id=case_id))


@bp.get("/admin/cases/disputes/<int:case_id>")
@require_role("admin")
def dispute(case_id):
    c = returns.get_case(case_id)
    audit.record(current_user(), "dispute.view", "return_case", c.id)
    from ...extensions import db
    db.session.commit()
    return render_template("admin/cases/dispute.html", c=c, amount=returns.refund_amount(c))


@bp.post("/admin/cases/disputes/<int:case_id>/decide")
@require_role("admin")
def decide(case_id):
    f = request.form
    returns.decide_dispute(current_user(), case_id, f.get("outcome"), f.get("reason_code"),
                           f.get("amount_vnd", type=int), f.get("note", ""))
    flash("Decision recorded", "success")
    return redirect(url_for("cases.dispute", case_id=case_id))


@bp.post("/admin/cases/orders/<int:order_id>/resolve")
@require_role("admin")
def resolve_order(order_id):
    service.resolve_order_dispute(current_user(), order_id, request.form.get("refund") == "1", request.form.get("reason_code"))
    flash("Order dispute resolved", "success")
    return redirect(url_for("cases.dashboard"))


@bp.post("/orders/<int:order_id>/help")
@require_role("customer")
def open_from_order(order_id):
    service.open_case(current_user(), order_id, f"Question about order #{order_id}", request.form.get("body"))
    flash("We've opened a case. An admin will review it.", "success")
    return redirect(url_for("order.detail", order_id=order_id))


@bp.post("/orders/<int:order_id>/not-received")
@require_role("customer")
def not_received(order_id):
    service.report_not_received(current_user(), order_id, request.form.get("statement"))
    flash("We've opened a case. An admin will review it.", "warning")
    return redirect(url_for("order.detail", order_id=order_id))
