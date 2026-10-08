from __future__ import annotations

from flask import Blueprint, render_template, request

from ...auth import current_user
from ..catalog import service as catalog
from . import service
from .images import SAMPLE_IMAGES
from .query import build_query

bp = Blueprint("search", __name__)


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
    q = build_query(mode, text=a.get("q", ""), image_key=a.get("image"), filters=filters, sort=a.get("sort", "relevance"))
    u = current_user()
    customer = u if u and u.role == "customer" else None
    result = service.search(q, customer)
    if customer and a.get("q", "").strip():
        try:
            from ..cart import service as cart
            cart.record_search(customer, a.get("q").strip())
        except ImportError:
            pass
    return render_template("customer/search.html", result=result, q=q, args=a, mode=mode,
                           sample_images=SAMPLE_IMAGES, categories=catalog.category_tree())
