from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for

from ...auth import current_user, require_role
from . import service

bp = Blueprint("notification", __name__)


@bp.get("/notifications")
@require_role()
def inbox():
    return render_template("customer/notifications.html", items=service.inbox(current_user()))


@bp.post("/notifications/<int:notification_id>/read")
@require_role()
def read(notification_id):
    service.mark_read(current_user(), notification_id)
    return redirect(url_for("notification.inbox"))


@bp.post("/notifications/read-all")
@require_role()
def read_all():
    service.mark_all_read(current_user())
    return redirect(url_for("notification.inbox"))
