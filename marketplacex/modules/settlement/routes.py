from __future__ import annotations

from flask import Blueprint, render_template

from ...auth import require_role
from . import service

bp = Blueprint("settlement", __name__)


@bp.get("/seller/settlement")
@require_role("seller")
def seller_statement():
    from ..seller.routes import current_shop
    shop = current_shop()
    return render_template("seller/settlement.html", st=service.statement(shop) if shop else None)
