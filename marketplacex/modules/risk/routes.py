from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from . import service

bp = Blueprint("risk", __name__, url_prefix="/risk")


@bp.get("/")
@require_role("risk")
def dashboard():
    status = request.args.get("status", "open")
    return render_template("risk/dashboard.html", alerts=service.alerts(None if status == "all" else status), status=status)


@bp.get("/alerts/<int:alert_id>")
@require_role("risk")
def alert(alert_id):
    a = service.get_alert(alert_id)
    return render_template("risk/alert.html", a=a, history=service.customer_history(a.customer_id) if a.customer_id else {})


@bp.post("/alerts/<int:alert_id>/<action>")
@require_role("risk")
def decide(alert_id, action):
    if action == "release":
        service.release(current_user(), alert_id, request.form.get("reason"))
        flash("Released — the transaction continues", "success")
    else:
        service.reject(current_user(), alert_id, request.form.get("reason"))
        flash("Rejected — holds were compensated", "warning")
    return redirect(url_for("risk.alert", alert_id=alert_id))
