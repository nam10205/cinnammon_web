"""Weighted scoring from report §10.2."""
from __future__ import annotations

import math
from datetime import timedelta

from ..admin import policy
from .query import Query, stem, tokenize

TEXT_WEIGHTS = {"lexical": 0.55, "semantic": 0.20, "offer": 0.10, "seller": 0.08, "delivery": 0.05, "fresh": 0.02}
IMAGE_WEIGHTS = {"lexical": 0.0, "semantic": 0.75, "offer": 0.10, "seller": 0.08, "delivery": 0.05, "fresh": 0.02}


def cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _fraction(terms: list[str], tokens: set, alts: dict | None = None) -> float:
    if not terms:
        return 0.0
    alts = alts or {}

    def hit(t: str) -> bool:
        return stem(t) in tokens or any(all(stem(w) in tokens for w in alt) for alt in alts.get(t, []))

    return sum(1 for t in terms if hit(t)) / len(terms)


def lexical(q: Query, product) -> float:
    text = " ".join([product.title, product.brand or "", product.category.name,
                     " ".join(str(v) for v in (product.attributes or {}).values())])
    return _fraction(q.terms, set(tokenize(text)), q.alts)


def features(q: Query, product, offer, shop, customer_city: str | None) -> dict:
    semantic = cosine(q.vector, product.image_vector) if q.vector else _fraction(q.terms, set(tokenize(product.description or "")), q.alts)
    return {
        "lexical": lexical(q, product) if not q.vector else 0.0,
        "semantic": semantic,
        "offer": (offer.rating_avg or 0) / 5.0,
        "seller": 1.0 if shop.verification_status == "verified" else 0.5,
        "delivery": 1.0 if customer_city and customer_city.lower() == shop.location.lower() else 0.5,
        "fresh": 1.0 if product.created_at and product.created_at >= policy.now() - timedelta(days=30) else 0.5,
    }


def score(q: Query, product, offer, shop, customer_city: str | None) -> float:
    f = features(q, product, offer, shop, customer_city)
    w = IMAGE_WEIGHTS if q.vector else TEXT_WEIGHTS
    return round(sum(w[k] * f[k] for k in w), 4)
