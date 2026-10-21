from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ... import auth
from ..catalog import service as catalog
from ..order import service as orders
from . import service

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("")
@auth.require_role("admin")
def dashboard():
    return render_template("admin/dashboard.html", counts=service.table_counts())


@bp.route("/categories", methods=["GET", "POST"])
@auth.require_role("admin")
def categories():
    if request.method == "POST":
        catalog.save_category(None, request.form.get("name", ""), request.form.get("description", ""))
        flash("Category added.", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/categories.html", rows=service.category_rows())


@bp.post("/categories/<int:category_id>")
@auth.require_role("admin")
def edit_category(category_id):
    catalog.save_category(catalog.get_category(category_id), request.form.get("name", ""),
                          request.form.get("description", ""))
    flash("Category saved.", "success")
    return redirect(url_for("admin.categories"))


@bp.post("/categories/<int:category_id>/delete")
@auth.require_role("admin")
def delete_category(category_id):
    catalog.delete_category(category_id)
    flash("Category deleted.", "success")
    return redirect(url_for("admin.categories"))


@bp.get("/customers")
@auth.require_role("admin")
def customers():
    return render_template("admin/customers.html", rows=service.customer_rows())


@bp.get("/customers/<int:customer_id>")
@auth.require_role("admin")
def customer(customer_id):
    c = service.get_customer(customer_id)
    orders.advance_due()
    return render_template("admin/customer.html", customer=c, orders=service.customer_orders(c),
                           searches=service.customer_searches(c))


@bp.get("/orders", endpoint="orders")
@auth.require_role("admin")
def orders_list():
    orders.advance_due()
    return render_template("admin/orders.html", orders=service.all_orders())


@bp.post("/orders/<int:order_id>/cancel")
@auth.require_role("admin")
def cancel_order(order_id):
    orders.cancel(orders.get_order(order_id))
    flash("Order cancelled.", "success")
    return redirect(url_for("admin.orders"))
