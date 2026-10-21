from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ... import auth
from ...extensions import db
from ..catalog import service as catalog
from ..catalog.models import ProductImage
from ..order import service as orders
from ..order.models import Order

bp = Blueprint("seller", __name__, url_prefix="/seller")


@bp.get("/products")
@auth.require_role("seller")
def products():
    q = request.args.get("q", "")
    cat = request.args.get("category", type=int)
    page = request.args.get("page", 1, type=int)
    items, total = catalog.seller_products(q, cat, page)
    return render_template("seller/products.html", items=items, total=total, q=q, category_id=cat,
                           page=page, categories=catalog.categories())


def _save(product):
    f = request.form
    return catalog.save_product(product, f.get("category_id", type=int) or 0, f.get("title", ""),
                                f.get("brand", ""), f.get("description", ""),
                                f.get("price", ""), f.get("stock", ""))


@bp.route("/products/new", methods=["GET", "POST"])
@auth.require_role("seller")
def new_product():
    if request.method == "POST":
        p = _save(None)
        flash("Product created. Add images below.", "success")
        return redirect(url_for("seller.edit_product", product_id=p.id))
    return render_template("seller/product_form.html", product=None, categories=catalog.categories())


@bp.route("/products/<int:product_id>", methods=["GET", "POST"])
@auth.require_role("seller")
def edit_product(product_id):
    product = catalog.get_product(product_id)
    if request.method == "POST":
        _save(product)
        flash("Product saved.", "success")
        return redirect(url_for("seller.edit_product", product_id=product.id))
    return render_template("seller/product_form.html", product=product, categories=catalog.categories())


@bp.post("/products/<int:product_id>/images")
@auth.require_role("seller")
def add_image(product_id):
    catalog.add_image(catalog.get_product(product_id), request.form.get("url", ""))
    flash("Image added.", "success")
    return redirect(url_for("seller.edit_product", product_id=product_id))


@bp.post("/images/<int:image_id>/delete")
@auth.require_role("seller")
def delete_image(image_id):
    image = db.session.get(ProductImage, image_id)
    pid = image.product_id if image else None
    catalog.remove_image(image_id)
    flash("Image removed.", "success")
    return redirect(url_for("seller.edit_product", product_id=pid))


@bp.get("/orders", endpoint="orders")
@auth.require_role("seller")
def order_list():
    orders.advance_due()
    rows = db.session.query(Order).order_by(Order.ordered_at.desc(), Order.id.desc()).all()
    return render_template("seller/orders.html", orders=rows)


@bp.post("/orders/<int:order_id>/skip")
@auth.require_role("seller")
def skip(order_id):
    orders.skip_step(orders.get_order(order_id))
    return redirect(url_for("seller.orders"))
