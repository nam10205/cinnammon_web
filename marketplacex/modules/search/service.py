"""Search pipeline: hard filters, candidate match, ranking, facets, trace (report §10.1, UC01)."""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from ...extensions import db
from ..admin import policy
from ..catalog import service as catalog
from ..catalog.models import Product
from ..inventory import service as inventory
from .models import SearchTrace
from .query import Query, build_query
from .ranking import cosine, lexical, score


@dataclass
class ResultItem:
    offer: object
    product: object
    shop: object
    score: float
    trace_id: str
    stock: int


@dataclass
class SearchResult:
    items: list = field(default_factory=list)
    facets: dict = field(default_factory=dict)
    relax_hints: list = field(default_factory=list)
    trace_id: str = ""
    degraded: bool = False
    query: Query | None = None


def _customer_city(customer):
    if customer is None:
        return None
    from ..identity.service import default_address
    a = default_address(customer)
    return a.city if a else None


def _passes_filters(q: Query, o, p, stock: int) -> bool:
    f = q.filters
    if q.max_price is not None and o.price_vnd > q.max_price:
        return False
    if q.min_price is not None and o.price_vnd < q.min_price:
        return False
    if f.get("category_id"):
        allowed = catalog.category_and_descendants(catalog.get_category(int(f["category_id"])))
        if p.category_id not in allowed:
            return False
    if f.get("brand") and p.brand.lower() != str(f["brand"]).lower():
        return False
    if f.get("min_rating") and o.rating_avg < float(f["min_rating"]):
        return False
    if f.get("location") and o.shop.location.lower() != str(f["location"]).lower():
        return False
    if f.get("in_stock") and stock <= 0:
        return False
    return True


SORT_KEYS = {
    "sales": lambda i: (-i.offer.sold_count, i.offer.id),
    "rating": lambda i: (-i.offer.rating_avg, i.offer.id),
    "newest": lambda i: (-i.product.created_at.timestamp(), i.offer.id),
    "price_asc": lambda i: (i.offer.price_vnd, i.offer.id),
    "price_desc": lambda i: (-i.offer.price_vnd, i.offer.id),
    "relevance": lambda i: (-i.score, i.offer.id),
}


def _relax_hints(q: Query) -> list[str]:
    hints = []
    if q.max_price is not None:
        hints.append(f"Remove price limit under {q.max_price:,} ₫")
    if q.min_price is not None:
        hints.append(f"Remove minimum price {q.min_price:,} ₫")
    labels = {"category_id": "category filter", "brand": "brand filter", "min_rating": "minimum rating",
              "location": "shop location filter", "in_stock": "in-stock only"}
    for k in q.filters:
        if k in labels:
            hints.append(f"Remove {labels[k]}")
    if q.terms:
        hints.append("Try fewer or different keywords")
    return hints


def search(q: Query, customer=None) -> SearchResult:
    trace_id = uuid.uuid4().hex[:12]
    city = _customer_city(customer)
    items = []
    for o in catalog.active_offers().all():
        p = o.product
        stock = inventory.in_stock(o.id)
        if not _passes_filters(q, o, p, stock):
            continue
        if q.vector is not None:
            if cosine(q.vector, p.image_vector) < 0.8:
                continue
        elif q.terms and lexical(q, p) <= 0:
            continue
        items.append(ResultItem(o, p, o.shop, score(q, p, o, o.shop, city), trace_id, stock))
    sort = q.sort
    if sort == "relevance" and not q.terms and q.vector is None:
        sort = "sales"
    items.sort(key=SORT_KEYS[sort])
    facets = {
        "category": Counter(i.product.category.name for i in items).most_common(),
        "brand": Counter(i.product.brand for i in items).most_common(),
        "location": Counter(i.shop.location for i in items).most_common(),
    }
    res = SearchResult(items=items, facets=facets, trace_id=trace_id, degraded=q.degraded, query=q)
    if not items:
        res.relax_hints = _relax_hints(q)
    db.session.add(SearchTrace(trace_id=trace_id, customer_id=getattr(customer, "id", None), query_json=q.as_dict(),
                               result_count=len(items), degraded=q.degraded, at=policy.now()))
    db.session.commit()
    return res


def _recently_purchased_offer_ids(customer) -> set:
    try:
        from ..order.models import Order, OrderItem
    except ImportError:
        return set()
    since = policy.now() - timedelta(days=30)
    rows = (OrderItem.query.join(Order).filter(Order.customer_id == customer.id, Order.created_at >= since,
                                               Order.status.notin_(["Cancelled", "PaymentFailed"])).all())
    return {r.offer_id for r in rows}


def recommend(customer, limit: int = 6) -> list[tuple]:
    """Recommendations with an explanation category (FR09). Suppresses recently purchased items."""
    out: list[tuple] = []
    seen: set = set()
    exclude = _recently_purchased_offer_ids(customer) if customer else set()

    def add(o, reason):
        if o.id in seen or o.id in exclude or len(out) >= limit:
            return
        seen.add(o.id)
        out.append((o, reason))

    if customer is not None:
        try:
            from ..cart import service as cart
            recent = cart.recent_searches(customer)
            if recent:
                text = recent[0].query_text
                for i in search(build_query("text", text), None).items[:2]:
                    add(i.offer, f"Because you searched '{text}'")
            for s in cart.saved(customer):
                if s.kind == "product":
                    p = db.session.get(Product, s.target_id)
                    if p:
                        for o in catalog.offers_in_categories([p.category_id])[:3]:
                            if o.product.id != p.id:
                                add(o, "Similar to items you saved")
        except ImportError:
            pass
    for o in catalog.popular_offers(limit + len(exclude) + 6):
        add(o, "Popular now")
    return out
