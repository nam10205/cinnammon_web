from __future__ import annotations

from flask import Blueprint, render_template

from ...auth import require_role

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@require_role("admin")
def dashboard():
    return render_template("admin/dashboard.html")
