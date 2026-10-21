from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ... import auth
from ...errors import ValidationError
from ..catalog import service as catalog
from . import images, service

bp = Blueprint("search", __name__)


def _render(products, heading, q=""):
    cust = auth.current_customer()
    return render_template("customer/search.html", products=products, heading=heading, q=q,
                           history=service.recent(cust))


@bp.get("/search")
def search():
    similar = request.args.get("similar", type=int)
    if similar is not None:
        p = catalog.get_product(similar)
        vec = p.image_vector
        return _render(service.search_vector(vec, exclude_id=p.id) if vec else [], f"Similar to {p.title}")
    q = request.args.get("q", "").strip()
    mode = request.args.get("mode", "text")
    if mode not in ("text", "voice"):
        mode = "text"
    if not q:
        return _render([], "Search", q)
    service.record(auth.current_customer(), q, mode)
    return _render(service.search_text(q), f"Results for “{q}”", q)


@bp.post("/search/image")
def search_image():
    f = request.files.get("photo")
    data = f.read() if f else b""
    if not data:
        flash("Choose a photo to search with", "warning")
        return redirect(url_for("search.search"))
    try:
        vec = images.feature_vector(data)
    except ValidationError as e:
        flash(e.message, "danger")
        return redirect(url_for("search.search"))
    service.record(auth.current_customer(), f.filename or "photo", "image")
    return _render(service.search_vector(vec), "Results for your photo")
