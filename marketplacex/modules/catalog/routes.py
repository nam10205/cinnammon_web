from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("catalog", __name__)


@bp.get("/")
def home():
    return render_template("customer/home.html")
