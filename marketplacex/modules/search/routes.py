from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request

from ...auth import current_user
from ...errors import NotFound, ValidationError
from ..catalog import service as catalog
from ..catalog.models import Product
from ...extensions import db
from . import service
from .images import feature_vector
from .query import build_query

bp = Blueprint("search", __name__)


def _customer():
    u = current_user()
    return u if u and u.role == "customer" else None


def _render(result, q, args, mode, photo_upload=False):
    return render_template("customer/search.html", result=result, q=q, args=args, mode=mode,
                           photo_upload=photo_upload,
                           categories=catalog.category_tree())


@bp.get("/search")
def search():
    a = request.args
    mode = a.get("mode", "text")
    filters = {
        "category_id": a.get("category", type=int), "brand": a.get("brand") or None,
        "min_rating": a.get("min_rating", type=float), "location": a.get("location") or None,
        "in_stock": bool(a.get("in_stock")), "max_price": a.get("max_price", type=int),
        "min_price": a.get("min_price", type=int),
    }
    vector = None
    if a.get("similar", type=int):
        mode = "image"
        product = db.session.get(Product, a.get("similar", type=int))
        if product is None:
            raise NotFound("Product not found")
        vector = product.image_vector
    q = build_query(mode, text=a.get("q", ""), image_vector=vector, filters=filters, sort=a.get("sort", "relevance"))
    customer = _customer()
    # Recorded first: its commit would otherwise expire every row the search loaded for rendering.
    if customer and mode != "image" and a.get("q", "").strip():
        try:
            from ..cart import service as cart
            cart.record_search(customer, a.get("q").strip())
        except ImportError:
            pass
    result = service.search(q, customer)
    return _render(result, q, a, mode)


@bp.post("/search/image")
def search_image():
    photo = request.files.get("photo")
    data = photo.read() if photo else b""
    if not data:
        flash("Choose a photo to search with", "danger")
        return redirect("/search?mode=image")
    try:
        vector = feature_vector(data)
    except ValidationError as e:
        flash(e.message, "danger")
        return redirect("/search?mode=image")
    q = build_query("image", image_vector=vector)
    customer = _customer()
    if customer:
        from ..cart import service as cart
        cart.record_search(customer, "[image]", "image")
    result = service.search(q, customer)
    return _render(result, q, request.args, "image", photo_upload=True)
