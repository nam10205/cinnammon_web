from __future__ import annotations

from sqlalchemy.orm import selectinload

from ... import clock
from ...extensions import db
from ..catalog.models import Product
from .models import SearchHistory
from .query import build_query
from .ranking import cosine, lexical

IMAGE_MATCH_THRESHOLD = 0.5
MAX_RESULTS = 48


def _products() -> list[Product]:
    return (db.session.query(Product).options(selectinload(Product.images), selectinload(Product.category))
            .order_by(Product.id).all())


def search_text(text: str) -> list[Product]:
    q = build_query("text", text=text)
    if not q.terms:
        return []
    scored = []
    for p in _products():
        if q.max_price is not None and p.price > q.max_price:
            continue
        s = lexical(q, p)
        phrase = text.strip().lower()
        if phrase in (p.title or "").lower():
            s += 100  # exact phrase, accents included, ranks first
        elif phrase in (p.description or "").lower():
            s += 50
        if s > 0:
            scored.append((s, p))
    scored.sort(key=lambda t: (-t[0], -(t[1].avg_rating or 0), t[1].id))
    return [p for _, p in scored[:MAX_RESULTS]]


def search_vector(vector: list[float], exclude_id: int | None = None) -> list[Product]:
    scored = []
    for p in _products():
        if p.id == exclude_id:
            continue
        s = cosine(vector, p.image_vector)
        if s >= IMAGE_MATCH_THRESHOLD:
            scored.append((s, p))
    scored.sort(key=lambda t: (-t[0], t[1].id))
    return [p for _, p in scored[:MAX_RESULTS]]


def record(customer, keyword: str, search_type: str) -> None:
    keyword = (keyword or "").strip()[:255]
    if customer is None or not keyword:
        return
    db.session.add(SearchHistory(customer_id=customer.id, keyword=keyword, search_type=search_type,
                                 searched_at=clock.now()))
    db.session.commit()


def recent(customer, limit: int = 8) -> list[SearchHistory]:
    if customer is None:
        return []
    return (db.session.query(SearchHistory).filter(SearchHistory.customer_id == customer.id)
            .order_by(SearchHistory.searched_at.desc(), SearchHistory.id.desc()).limit(limit).all())


def recent_keywords(customer, limit: int = 8) -> list[dict]:
    """Distinct typed or spoken searches, newest first, for the search box dropdown."""
    if customer is None:
        return []
    out, seen = [], set()
    rows = (db.session.query(SearchHistory.keyword, SearchHistory.search_type)
            .filter(SearchHistory.customer_id == customer.id, SearchHistory.search_type.in_(("text", "voice")))
            .order_by(SearchHistory.searched_at.desc(), SearchHistory.id.desc()).limit(limit * 5))
    for keyword, kind in rows:
        key = keyword.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append({"q": keyword, "type": kind})
        if len(out) == limit:
            break
    return out
