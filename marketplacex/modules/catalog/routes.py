from __future__ import annotations

from flask import Blueprint, render_template, request

from ...auth import current_user
from ..inventory import service as inventory
from ..seller import service as seller_service
from . import service

bp = Blueprint("catalog", __name__)


def _customer_city():
    u = current_user()
    if u is None:
        return None
    from ..identity.service import default_address
    a = default_address(u)
    return a.city if a else None


def _home_extras():
    extras = {"campaigns": [], "recommendations": []}
    try:
        from ..promotion import service as promo
        extras["campaigns"] = promo.active_campaigns()
    except ImportError:
        pass
    try:
        from ..search import service as search
        u = current_user()
        extras["recommendations"] = search.recommend(u if u and u.role == "customer" else None)
    except ImportError:
        pass
    return extras


@bp.get("/")
def home():
    return render_template("customer/home.html", categories=service.category_tree(),
                           popular=service.popular_offers(12), **_home_extras())


@bp.get("/category/<int:category_id>")
def category(category_id):
    c = service.get_category(category_id)
    offers = service.offers_in_categories(service.category_and_descendants(c))
    return render_template("customer/category.html", category=c, offers=offers, categories=service.category_tree())


@bp.get("/shops/<int:shop_id>")
def shop(shop_id):
    s = seller_service.get_shop(shop_id)
    return render_template("customer/shop.html", shop=s, offers=service.offers_of_shop(shop_id))


@bp.get("/products/<int:product_id>")
def product(product_id):
    p = service.get_product(product_id)
    u = current_user()
    if p.status != "active" and not (u and (u.role == "admin" or p.shop.owner_id == u.id)):
        from ...errors import NotFound
        raise NotFound("Product not available")
    sel = request.args.get("variant", type=int)
    offers = [v.offer for v in p.variants]
    offer = next((o for o in offers if o.variant_id == sel), offers[0])
    reviews = []
    try:
        from ..review import service as review_service
        reviews = review_service.reviews_for_product(p.id)
    except ImportError:
        pass
    return render_template("customer/product.html", product=p, offer=offer, offers=offers,
                           stock=inventory.in_stock(offer.id),
                           promise=service.delivery_promise(offer, _customer_city()), reviews=reviews)
