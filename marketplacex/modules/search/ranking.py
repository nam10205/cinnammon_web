"""Scoring helpers for text and image search."""
from __future__ import annotations

import math

from .query import Query, stem, tokenize


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
    text = " ".join([product.title, product.brand or "", product.category.name, product.description or ""])
    return _fraction(q.terms, set(tokenize(text)), q.alts)
