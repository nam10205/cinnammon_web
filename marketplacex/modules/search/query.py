"""Common query object: text, voice transcript and image all become one Query (report §10.1, FR03)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

SYNONYMS = {"khong day": "wireless", "giay": "shoes", "chay": "running", "bo": "", "mau": "", "den": "black",
            "trang": "white", "chuot": "mouse", "ao": "shirt"}
STOPWORDS = {"under", "below", "duoi", "for", "the", "a", "an", "with", "in", "of"}
PRICE_RE = re.compile(r"\b(?:under|below|duoi)\s+(\d+(?:[.,]\d+)?)\s*(million|trieu|tr|m|k|nghin)?\b")
SORTS = ("relevance", "sales", "rating", "newest", "price_asc", "price_desc")


@dataclass
class Query:
    type: str
    raw: str
    terms: list = field(default_factory=list)
    max_price: int | None = None
    min_price: int | None = None
    vector: list | None = None
    filters: dict = field(default_factory=dict)
    sort: str = "relevance"
    degraded: bool = False
    alts: dict = field(default_factory=dict)  # term -> Vietnamese tokens that also satisfy it

    def as_dict(self) -> dict:
        return {"type": self.type, "raw": self.raw, "terms": self.terms, "max_price": self.max_price,
                "min_price": self.min_price, "vector": self.vector, "filters": self.filters, "sort": self.sort,
                "degraded": self.degraded}


def strip_diacritics(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def normalize(s: str) -> str:
    s = strip_diacritics((s or "").lower())
    return re.sub(r"[^a-z0-9.,\s]", " ", s)


def stem(tok: str) -> str:
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") else tok


def tokenize(s: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", normalize(s))]


def _parse_price(text: str) -> tuple[str, int | None]:
    m = PRICE_RE.search(text)
    if not m:
        return text, None
    n = float(m.group(1).replace(",", "."))
    unit = m.group(2)
    if unit in ("million", "trieu", "tr", "m"):
        n *= 1_000_000
    elif unit in ("k", "nghin"):
        n *= 1_000
    return text[:m.start()] + " " + text[m.end():], int(n)


def _terms(text: str) -> tuple[list[str], dict]:
    """Return (terms, alts). A synonym is an alternative: the English term also matches via its Vietnamese words."""
    toks = re.findall(r"[a-z0-9]+", text)
    out: list[str] = []
    alts: dict = {}
    keys = sorted(SYNONYMS, key=lambda k: -len(k.split()))
    i = 0
    while i < len(toks):
        for k in keys:
            n = len(k.split())
            if toks[i:i + n] == k.split():
                term, orig, i = SYNONYMS[k], toks[i:i + n], i + n
                break
        else:
            term, orig, i = toks[i], None, i + 1
        if not term or term in STOPWORDS:
            continue
        if orig:
            alts.setdefault(term, [])
            if orig != [term] and orig not in alts[term]:
                alts[term].append(orig)
        if term not in out:
            out.append(term)
    return out, alts


def build_query(mode: str, text: str = "", image_vector: list[float] | None = None, filters: dict | None = None,
                sort: str = "relevance") -> Query:
    mode = mode if mode in ("text", "voice", "image") else "text"
    q = Query(type=mode, raw=text or "", filters={k: v for k, v in (filters or {}).items() if v not in (None, "")},
              sort=sort if sort in SORTS else "relevance")
    if mode == "image":
        if not image_vector:
            # Image encoding failed: fall back to text and mark the response degraded (report §4.2).
            q.type, q.degraded = "text", True
        else:
            q.vector = list(image_vector)
    norm = normalize(text)
    norm, q.max_price = _parse_price(norm)
    q.terms, q.alts = _terms(norm)
    if q.filters.get("max_price") is not None:
        q.max_price = int(q.filters.pop("max_price"))
    if q.filters.get("min_price") is not None:
        q.min_price = int(q.filters.pop("min_price"))
    return q
