"""Data access objects from the search sequence diagrams: SearchHistoryDAO, ProductDAO and ProductImageDAO.
They only read and write rows; deciding what to search and what to save is SearchController's job."""
from __future__ import annotations

from sqlalchemy.orm import selectinload

from ...extensions import db
from ..catalog.models import Product, ProductImage
from .images import unpack
from .models import SearchHistory
from .query import build_query
from .ranking import cosine, lexical

IMAGE_MATCH_THRESHOLD = 0.5
MAX_RESULTS = 48


class SearchHistoryDAO:
    @staticmethod
    def find_recent(customer_id: int, limit: int = 8) -> list[SearchHistory]:
        """findRecent(customerId, limit): newest first, every search type."""
        return (db.session.query(SearchHistory).filter(SearchHistory.customer_id == customer_id)
                .order_by(SearchHistory.searched_at.desc(), SearchHistory.id.desc()).limit(limit).all())

    @staticmethod
    def find_recent_keywords(customer_id: int, limit: int = 8) -> list[SearchHistory]:
        """Distinct typed or spoken keywords, newest first, for the dropdown under the search box."""
        out, seen = [], set()
        rows = (db.session.query(SearchHistory)
                .filter(SearchHistory.customer_id == customer_id, SearchHistory.search_type.in_(("text", "voice")))
                .order_by(SearchHistory.searched_at.desc(), SearchHistory.id.desc()).limit(limit * 5))
        for h in rows:
            key = h.keyword.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(h)
            if len(out) == limit:
                break
        return out

    @staticmethod
    def save(history: SearchHistory) -> None:
        db.session.add(history)
        db.session.commit()


class ProductDAO:
    @staticmethod
    def _all() -> list[Product]:
        return (db.session.query(Product).options(selectinload(Product.images), selectinload(Product.category))
                .order_by(Product.id).all())

    @staticmethod
    def find_by_keyword(keyword: str) -> list[Product]:
        """findByKeyword(keyword): accent-blind word match over title, brand, category and description."""
        q = build_query("text", text=keyword)
        if not q.terms:
            return []
        phrase = keyword.strip().lower()
        scored = []
        for p in ProductDAO._all():
            if q.max_price is not None and p.price > q.max_price:
                continue
            s = lexical(q, p)
            if phrase in (p.title or "").lower():
                s += 100  # exact phrase, accents included, ranks first
            elif phrase in (p.description or "").lower():
                s += 50
            if s > 0:
                scored.append((s, p))
        scored.sort(key=lambda t: (-t[0], -(t[1].avg_rating or 0), t[1].id))
        return [p for _, p in scored[:MAX_RESULTS]]

    @staticmethod
    def find_by_id(product_id: int) -> Product | None:
        return db.session.get(Product, product_id)


class ProductImageDAO:
    @staticmethod
    def find_similar(feature_vector: list[float], exclude_product_id: int | None = None) -> list[ProductImage]:
        """findSimilar(featureVector): the best-matching image of each product, closest colours first."""
        best: dict[int, tuple[float, ProductImage]] = {}
        rows = (db.session.query(ProductImage).options(selectinload(ProductImage.product))
                .filter(ProductImage.feature_vector.isnot(None)))
        for img in rows:
            if img.product_id == exclude_product_id:
                continue
            s = cosine(feature_vector, unpack(img.feature_vector))
            if s >= IMAGE_MATCH_THRESHOLD and s > best.get(img.product_id, (0.0, None))[0]:
                best[img.product_id] = (s, img)
        ranked = sorted(best.values(), key=lambda t: (-t[0], t[1].product_id))
        return [img for _, img in ranked[:MAX_RESULTS]]
