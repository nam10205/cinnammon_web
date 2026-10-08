from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ...errors import NotFound
from ..order import service as order_service
from . import service

bp = Blueprint("review", __name__)


@bp.route("/orders/<int:order_id>/items/<int:item_id>/review", methods=["GET", "POST"])
@require_role("customer")
def write(order_id, item_id):
    o = order_service.get_for_customer(current_user(), order_id)
    item = next((i for i in o.items if i.id == item_id), None)
    if item is None:
        raise NotFound("Item not found")
    if request.method == "POST":
        service.create_review(current_user(), item.id, request.form.get("rating"), request.form.get("comment"))
        flash("Thanks for your review!", "success")
        return redirect(url_for("order.detail", order_id=o.id))
    return render_template("customer/review_form.html", o=o, item=item)


@bp.get("/seller/reviews")
@require_role("seller")
def seller_reviews():
    from ..seller.routes import current_shop
    shop = current_shop()
    return render_template("seller/reviews.html", reviews=service.reviews_for_shop(shop.id) if shop else [])


@bp.post("/seller/reviews/<int:review_id>/reply")
@require_role("seller")
def seller_reply(review_id):
    service.reply(current_user(), review_id, request.form.get("text"))
    flash("Reply posted", "success")
    return redirect(url_for("review.seller_reviews"))
