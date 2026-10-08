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


# --- Shop profile, listings, inventory --------------------------------------------------------------

from ..catalog import service as catalog  # noqa: E402
from ..inventory import service as inventory  # noqa: E402


@bp.route("/shop", methods=["GET", "POST"])
@require_role("seller")
def shop_profile():
    u = current_user()
    shop = current_shop()
    if request.method == "POST":
        f = request.form
        if f.get("action") == "create" or shop is None:
            shop = service.create_shop(u, f.get("name"), f.get("location"), f.get("description", ""))
            session["shop_id"] = shop.id
            flash("Shop created. Submit verification to start selling.", "success")
        else:
            service.update_shop(u, shop.id, f.get("name"), f.get("location"), f.get("description", ""))
            flash("Shop updated", "success")
        return redirect(url_for("seller.shop_profile"))
    return render_template("seller/shop.html", shop=shop)


@bp.post("/shop/verify")
@require_role("seller")
def shop_verify():
    service.submit_verification(current_user(), current_shop().id, request.form.get("info"))
    flash("Verification submitted for review", "success")
    return redirect(url_for("seller.shop_profile"))


@bp.get("/products")
@require_role("seller")
def products():
    shop = current_shop()
    return render_template("seller/products.html", products=catalog.products_of_shop(shop.id) if shop else [])


def _listing_form() -> dict:
    f = request.form
    attrs = dict(zip(f.getlist("attr_key"), f.getlist("attr_value")))
    variants = []
    for name, price, orig, stock, limit in zip(f.getlist("variant_name"), f.getlist("variant_price"),
                                               f.getlist("variant_original"), f.getlist("variant_stock"),
                                               f.getlist("variant_limit")):
        if not name.strip() and not price.strip():
            continue
        def num(x, default=0):
            return int(x) if x.strip().lstrip("-").isdigit() else default
        variants.append({"name": name.strip(), "price_vnd": num(price), "original_price_vnd": num(orig, None),
                         "stock": num(stock), "purchase_limit": num(limit, 10)})
    return {"category_id": f.get("category_id", type=int), "title": f.get("title"), "brand": f.get("brand", ""),
            "description": f.get("description", ""), "attributes": {k.strip(): v.strip() for k, v in attrs.items() if k.strip()},
            "variants": variants}


def _categories():
    out = []
    for c in catalog.category_tree():
        out.append(c)
        out.extend(c.children)
    return out


@bp.route("/products/new", methods=["GET", "POST"])
@require_role("seller")
def product_new():
    shop = current_shop()
    if request.method == "POST":
        p = catalog.save_listing(current_user(), shop.id, _listing_form(), submit=bool(request.form.get("submit")))
        flash("Listing submitted for moderation" if p.status == "pending" else "Draft saved", "success")
        return redirect(url_for("seller.products"))
    return render_template("seller/product_form.html", product=None, categories=_categories())


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@require_role("seller")
def product_edit(product_id):
    shop = current_shop()
    p = catalog.get_product(product_id)
    if shop is None or p.shop.owner_id != current_user().id:
        raise NotFound("Product not found")
    if request.method == "POST":
        p = catalog.save_listing(current_user(), p.shop_id, _listing_form(), product_id=p.id,
                                 submit=bool(request.form.get("submit")))
        flash(f"Listing saved ({p.status})", "success")
        return redirect(url_for("seller.products"))
    return render_template("seller/product_form.html", product=p, categories=_categories(),
                           stock={v.offer.id: inventory.in_stock(v.offer.id) for v in p.variants})


@bp.get("/inventory")
@require_role("seller")
def inventory_page():
    shop = current_shop()
    offers = catalog.offers_of_shop(shop.id, only_active=False) if shop else []
    return render_template("seller/inventory.html", offers=offers, ledgers={o.id: inventory.get_ledger(o.id) for o in offers})


@bp.post("/inventory/<int:offer_id>")
@require_role("seller")
def inventory_update(offer_id):
    f = request.form
    service.update_offer(current_user(), offer_id, f.get("price_vnd", type=int) or 0, f.get("original_price_vnd") or None,
                         f.get("stock", type=int) if f.get("stock", type=int) is not None else -1,
                         f.get("purchase_limit", type=int) or 0, f.get("version", type=int))
    flash("Offer updated", "success")
    return redirect(url_for("seller.inventory_page"))
