"""HTTP side of the search diagrams. SearchView is the header search box (base.html with search_view.js and
voice_search_view.js), ImageSearchView is the photo panel (image_search_view.js) and SearchResultView is
customer/search.html. Every route hands straight to SearchController."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from ... import auth
from ...errors import ValidationError
from ..catalog import service as catalog
from .controller import InvalidKeyword, SearchController
from .dao import SearchHistoryDAO
from .query import SearchRegion

bp = Blueprint("search", __name__)


def _show_result_view(products, heading, q="", status=200, **extra):
    cust = auth.current_customer()
    history = SearchHistoryDAO.find_recent(cust.id) if cust else []
    return render_template("customer/search.html", products=products, heading=heading, q=q,
                           history=history, **extra), status


def _show_error(title, message, heading="Search", q="", **extra):
    return _show_result_view([], heading, q, status=400, popup_error={"title": title, "message": message}, **extra)


@bp.get("/search")
def search():
    similar = request.args.get("similar", type=int)
    if similar is not None:
        p = catalog.get_product(similar)
        return _show_result_view(SearchController.find_similar(p), f"Similar to {p.title}")
    if "q" not in request.args:  # the camera button lands here to search by photo
        return _show_result_view([], "Search")
    q = request.args.get("q", "")
    try:
        if request.args.get("mode") == "voice":
            products = SearchController.confirm_voice_text(auth.current_customer(), q)
        else:
            products = SearchController.search_by_keyword(auth.current_customer(), q)
    except InvalidKeyword as e:
        return _show_error("Invalid Keyword", e.message, q=q.strip())
    return _show_result_view(products, f"Results for “{q.strip()}”", q.strip())


@bp.get("/api/search/history")
def history():
    items = SearchController.show_search_box(auth.current_customer())
    return jsonify({"items": [{"q": h.keyword, "type": h.search_type} for h in items]})


@bp.post("/api/search/image/validate")
def validate_image():
    f = request.files.get("photo")
    try:
        width, height = SearchController.validate_image(f.read() if f else b"")
    except ValidationError as e:
        return jsonify({"ok": False, "title": "File error", "error": e.message}), 400
    return jsonify({"ok": True, "width": width, "height": height})


@bp.post("/search/image")
def search_image():
    f = request.files.get("photo")
    try:
        result = SearchController.search_by_image(
            auth.current_customer(), f.read() if f else b"", SearchRegion.from_form(request.form),
            f.filename if f else "", [c.name for c in catalog.categories()])
    except ValidationError as e:
        return _show_error("File error", e.message)
    return _show_result_view(result.products, "Results for your photo", search_box=result.label or "",
                             photo_note=result.note)
