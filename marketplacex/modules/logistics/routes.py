from __future__ import annotations

from flask import Blueprint, flash, redirect, request

from ...auth import current_user, require_role
from ...errors import NotFound
from . import service

bp = Blueprint("logistics", __name__)


@bp.post("/logistics/shipments/<int:shipment_id>/advance")
@require_role("customer", "seller", "admin")
def advance(shipment_id):
    """Fake carrier button shown on order pages (the carrier is an external actor)."""
    s = service.get_shipment(shipment_id)
    u = current_user()
    if u.role == "customer" and s.order.customer_id != u.id:
        raise NotFound("Shipment not found")
    if u.role == "seller" and s.order.shop.owner_id != u.id:
        raise NotFound("Shipment not found")
    ev = service.advance(s, fail=request.form.get("fail") == "1" or request.args.get("fail") == "1")
    flash(f"Carrier update: {ev.status.replace('_', ' ')}", "info")
    return redirect(request.referrer or "/")
