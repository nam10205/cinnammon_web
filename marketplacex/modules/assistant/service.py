"""Shopping assistant: answers customer questions with Gemini, grounded in our catalogue, policies and the
customer's own orders. It gives advice and links only; it never changes orders or payments."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from flask import current_app

from ...errors import DomainError

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RATE_LIMIT = 20          # messages
RATE_WINDOW_S = 600      # per 10 minutes
MAX_HISTORY = 10


class AssistantUnavailable(DomainError):
    code = "assistant_unavailable"
    status = 503


class AssistantRateLimited(DomainError):
    code = "rate_limited"
    status = 429


def check_rate(key: str) -> None:
    buckets = current_app.extensions.setdefault("assistant_rate", {})
    now = time.time()
    recent = [t for t in buckets.get(key, []) if now - t < RATE_WINDOW_S]
    if len(recent) >= RATE_LIMIT:
        raise AssistantRateLimited("You're sending messages too quickly. Please wait a few minutes.")
    recent.append(now)
    buckets[key] = recent


def _products_context(question: str) -> str:
    from ..catalog.models import Product
    from ..search import service as search
    from ...extensions import db
    items = search.search_text(question)[:8]
    if not items:
        top = db.session.query(Product).order_by(Product.avg_rating.desc(), Product.id).limit(5).all()
        return "No direct matches. Popular products:\n" + "\n".join(_product_line(p) for p in top)
    return "Matching products:\n" + "\n".join(_product_line(p) for p in items)


def _product_line(p) -> str:
    return (f"- {p.title} | {p.price:,} ₫ | rating {p.avg_rating or 0:.1f} | "
            f"{'in stock' if p.stock_quantity > 0 else 'out of stock'} | /products/{p.id}")


def _policy_context() -> str:
    return ("Shipping is 30,000 ₫ per checkout, and free from 500,000 ₫. "
            "Payment is cash on delivery or the demo card. "
            "Orders move placed, processing, shipped, delivered about every 20 seconds, "
            "and can be cancelled before they ship. "
            "Useful pages: /search, /cart, /checkout, /orders, /profile.")


def _orders_context(customer) -> str:
    if customer is None:
        return "The user is not logged in as a customer; you cannot see any orders."
    from ..order import service as order_service
    orders = [o for group in order_service.orders_for_customer(customer) for o in group][:8]
    if not orders:
        return f"Customer {customer.name} has no orders."
    lines = [f"- Order #{o.id}: {o.product.title} x{o.quantity}, {o.status}, "
             f"total {o.total_price:,} ₫ | /orders/{o.id}" for o in orders]
    return f"Customer {customer.name}'s recent orders (only this customer's):\n" + "\n".join(lines)


def build_system_prompt(question: str, customer) -> str:
    return (
        "You are the friendly shopping assistant of MarketplaceX, a small demo online shop in Vietnam. "
        "Answer briefly (2-5 sentences or a short list). Prices are in Vietnamese dong (₫). "
        "Only recommend products listed below and quote their exact prices; link them as markdown links "
        "like [Product name](/products/123). If something is not in the data, say you don't know. "
        "You cannot place, cancel or refund orders: explain which page to use instead. "
        "Reply in the customer's language (Vietnamese or English).\n\n"
        f"STORE INFO\n{_policy_context()}\n\n"
        f"CATALOGUE\n{_products_context(question)}\n\n"
        f"ORDERS\n{_orders_context(customer)}"
    )


def _gemini_keys() -> list[str]:
    keys = [current_app.config.get("GEMINI_API_KEY")] + list(current_app.config.get("GEMINI_API_KEYS") or [])
    return list(dict.fromkeys(k for k in keys if k))


def _call_gemini(system: str, contents: list, timeout: float = 30) -> str:
    """Free-tier keys have a small daily quota, so a key that answers 429 hands over to the next one."""
    keys = _gemini_keys()
    if not keys:
        raise AssistantUnavailable("The assistant is unavailable (no GEMINI_API_KEY configured).")
    body = json.dumps({"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                       "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024,
                                             "thinkingConfig": {"thinkingBudget": 0}}}).encode()
    url = GEMINI_URL.format(model=current_app.config.get("GEMINI_MODEL", "gemini-3.5-flash"))
    start = current_app.extensions.get("gemini_key", 0) % len(keys)
    for n in range(len(keys)):
        i = (start + n) % len(keys)
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": keys[i]})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            current_app.extensions["gemini_key"] = i
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                current_app.logger.warning("Gemini key %d of %d is out of quota, trying the next", i + 1, len(keys))
                continue
            current_app.logger.warning("Gemini call failed: %s", e)
            break
        except (OSError, KeyError, IndexError, ValueError) as e:  # OSError covers URLError and socket.timeout
            current_app.logger.warning("Gemini call failed: %s", e)
            break
    raise AssistantUnavailable("The assistant is temporarily unavailable. Please try again later.")


def ask(question: str, history: list, customer) -> str:
    contents = []
    for h in (history or [])[-MAX_HISTORY:]:
        role = "model" if h.get("role") == "model" else "user"
        text = str(h.get("text", ""))[:2000]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": question}]})
    return _call_gemini(build_system_prompt(question, customer), contents) or "Sorry, I don't have an answer for that."
