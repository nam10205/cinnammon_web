from __future__ import annotations

from collections import Counter

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ...auth import current_user, require_role
from ...errors import NotFound
from ..logistics import service as logistics
from ..logistics.models import Shipment
from ..order import service as order_service
from . import service

bp = Blueprint("seller", __name__, url_prefix="/seller")


def current_shop():
    u = current_user()
    shops = service.shops_of(u)
    if not shops:
        return None
    sid = session.get("shop_id")
    return next((s for s in shops if s.id == sid), shops[0])


@bp.app_context_processor
def _seller_ctx():
    u = current_user()
    if u is None or u.role != "seller":
        return {}
    return {"seller_shops": service.shops_of(u), "seller_shop": current_shop()}


@bp.post("/switch-shop")
@require_role("seller")
def switch_shop():
    s = service.owned_shop(current_user(), request.form.get("shop_id", type=int))
    session["shop_id"] = s.id
    return redirect(url_for("seller.dashboard"))


@bp.get("/")
@require_role("seller")
def dashboard():
    shop = current_shop()
    if shop is None:
        return render_template("seller/no_shop.html")
    orders = order_service.orders_of_shop(shop)
    counts = Counter(o.status for o in orders)
    overdue = [s for s in Shipment.query.join(Shipment.order).filter_by(shop_id=shop.id).all() if logistics.pickup_overdue(s)]
    return render_template("seller/dashboard.html", shop=shop, counts=counts, overdue=overdue,
                           todo=[o for o in orders if o.status in ("Confirmed", "Preparing", "ReadyToShip", "CancelRequested", "DeliveryException")])


@bp.get("/orders")
@require_role("seller")
def orders():
    shop = current_shop()
    if shop is None:
        return redirect(url_for("seller.dashboard"))
    status = request.args.get("status") or None
    return render_template("seller/orders.html", shop=shop, orders=order_service.orders_of_shop(shop, status), status=status)


@bp.get("/orders/<int:order_id>")
@require_role("seller")
def order_detail(order_id):
    o = order_service.get_for_shop_owner(current_user(), order_id)
    return render_template("seller/order_detail.html", o=o, overdue={s.id for s in o.shipments if logistics.pickup_overdue(s)})


@bp.post("/orders/<int:order_id>/<action>")
@require_role("seller")
def order_action(order_id, action):
    u = current_user()
    f = request.form
    if action == "accept":
        service.accept(u, order_id)
        flash("Order accepted", "success")
    elif action == "pack":
        s = service.pack(u, order_id, f.get("weight_g", type=int))
        flash(f"Label {s.tracking_no} created", "success")
    elif action == "handover":
        service.hand_over(u, order_id)
        flash("Handed over to carrier", "success")
    elif action == "reject":
        service.reject(u, order_id, f.get("reason"))
        flash("Order rejected; stock and payment released", "warning")
    elif action in ("cancel-approve", "cancel-decline"):
        service.resolve_cancel(u, order_id, action == "cancel-approve", f.get("reason"))
        flash("Cancellation resolved", "success")
    elif action == "reattempt":
        o = order_service.get_for_shop_owner(u, order_id)
        logistics.reattempt(u, next(s for s in o.shipments if s.kind == "forward"))
        flash("Delivery re-attempt scheduled", "success")
    else:
        raise NotFound("Unknown action")
    return redirect(url_for("seller.order_detail", order_id=order_id))


@bp.get("/labels/<tracking_no>")
@require_role("seller")
def label(tracking_no):
    s = Shipment.query.filter_by(tracking_no=tracking_no).first()
    if s is None or s.order.shop.owner_id != current_user().id:
        raise NotFound("Label not found")
    return render_template("seller/label.html", s=s)
