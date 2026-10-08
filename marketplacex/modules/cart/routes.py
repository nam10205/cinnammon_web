from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ...extensions import db
from ..catalog.models import Product
from ..seller.models import Shop
from . import service

bp = Blueprint("cart", __name__)


@bp.get("/cart")
@require_role("customer")
def view():
    c = service.get_cart(current_user())
    groups = service.grouped(c)
    return render_template("customer/cart.html", cart=c, groups=groups,
                           total=sum(g.subtotal_vnd for g in groups))


@bp.post("/cart/add")
@require_role("customer")
def add():
    service.add_item(current_user(), request.form.get("offer_id", type=int), service.parse_qty(request.form.get("qty", 1)))
    flash("Added to cart", "success")
    return redirect(request.referrer or url_for("cart.view"))


@bp.post("/cart/items/<int:offer_id>")
@require_role("customer")
def change(offer_id):
    service.change_item(current_user(), offer_id, service.parse_qty(request.form.get("qty")),
                        request.form.get("version", type=int))
    return redirect(url_for("cart.view"))


@bp.post("/cart/items/<int:offer_id>/select")
@require_role("customer")
def select(offer_id):
    service.set_selected(current_user(), offer_id, request.form.get("selected") == "1")
    return redirect(url_for("cart.view"))


@bp.post("/saved/toggle")
@require_role("customer")
def toggle_saved():
    on = service.toggle_saved(current_user(), request.form.get("kind"), request.form.get("target_id", type=int))
    flash("Saved" if on else "Removed from saved", "success")
    return redirect(request.referrer or url_for("cart.saved"))


@bp.get("/saved")
@require_role("customer")
def saved():
    u = current_user()
    items = service.saved(u)
    products = [db.session.get(Product, s.target_id) for s in items if s.kind == "product"]
    shops = [db.session.get(Shop, s.target_id) for s in items if s.kind == "shop"]
    return render_template("customer/saved.html", products=[p for p in products if p],
                           shops=[s for s in shops if s], recent=service.recent_searches(u))


@bp.post("/recent/<int:recent_id>/delete")
@require_role("customer")
def delete_recent(recent_id):
    service.delete_recent(current_user(), recent_id)
    return redirect(url_for("cart.saved"))
