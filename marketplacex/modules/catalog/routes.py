from __future__ import annotations

from flask import Blueprint, render_template, request

from . import service

bp = Blueprint("catalog", __name__)

PER_PAGE = 24


def _int_arg(name: str) -> int | None:
    try:
        return int(request.args[name])
    except (KeyError, ValueError):
        return None


@bp.get("/")
def home():
    return render_template("customer/home.html", sections=service.home_sections())


@bp.get("/categories/<int:category_id>")
def category(category_id):
    cat = service.get_category(category_id)
    sort = request.args.get("sort", "rating")
    if sort not in service.SORTS:
        sort = "rating"
    min_price, max_price = _int_arg("min_price"), _int_arg("max_price")
    page = _int_arg("page") or 1
    items, total = service.category_products(category_id, sort, min_price, max_price, page, PER_PAGE)
    pages = max(1, -(-total // PER_PAGE))
    return render_template("customer/category.html", category=cat, products=items, total=total,
                           sort=sort, min_price=min_price, max_price=max_price,
                           page=max(1, page), pages=pages)


@bp.get("/products/<int:product_id>")
def product(product_id):
    p = service.get_product(product_id)
    return render_template("customer/product.html", p=p, has_vector=bool(p.images and p.images[0].feature_vector))
