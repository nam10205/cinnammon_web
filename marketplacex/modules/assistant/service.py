"""Shopping assistant: answers customer questions with Gemini, grounded in our catalogue, policies and the
customer's own orders. It gives advice and links only; it never changes orders or payments."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from flask import current_app

from ...errors import DomainError
from ..admin import policy

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
    from ..search import service as search
    from ..search.query import build_query
    items = search.search(build_query("text", question), None).items[:8]
    if not items:
        items_txt = [f"- {o.product.title} | {o.price_vnd:,} ₫ | /products/{o.product.id}"
                     for o, _ in search.recommend(None, 5)]
        return "No direct matches. Popular products:\n" + "\n".join(items_txt)
    lines = []
    for i in items:
        lines.append(f"- {i.product.title} | {i.offer.price_vnd:,} ₫ | rating {i.offer.rating_avg:.1f} | "
                     f"{'in stock' if i.stock > 0 else 'out of stock'} | shop {i.shop.name} ({i.shop.location}) | "
                     f"/products/{i.product.id}")
    return "Matching products:\n" + "\n".join(lines)


def _policy_context() -> str:
    from ..promotion import service as promo
    vouchers = [f"{v.code}: {v.describe()}" + (f" (only at {v.shop.name})" if v.shop else "")
                for c in promo.active_campaigns() for v in c.vouchers]
    return (f"Return window: {policy.get_int('return_window_days')} days after delivery. "
            f"Sellers respond to return requests within {policy.get_int('seller_response_hours')} hours; "
            "unresolved cases can be escalated to MarketplaceX dispute review. "
            "Shipping is a flat 28,000 ₫ per shop. One checkout can include several shops; each shop becomes its own order. "
            "Orders can be cancelled before the seller packs them (later, the seller must approve). "
            "Active vouchers: " + ("; ".join(vouchers) or "none") + ". "
            "Useful pages: /search, /cart, /checkout, /orders, /saved, /chat (talk to sellers).")


def _orders_context(customer) -> str:
    if customer is None or customer.role != "customer":
        return "The user is not logged in as a customer; you cannot see any orders."
    from ..order import service as order_service
    orders = order_service.orders_of_customer(customer)[:8]
    if not orders:
        return f"Customer {customer.name} has no orders."
    lines = [f"- Order #{o.id} from {o.shop.name}: {o.status}, total {o.total_vnd:,} ₫, "
             f"items: {', '.join(i.title_snapshot for i in o.items)} | /orders/{o.id}" for o in orders]
    return f"Customer {customer.name}'s recent orders (only this customer's):\n" + "\n".join(lines)


def build_system_prompt(question: str, customer) -> str:
    return (
        "You are the friendly shopping assistant of MarketplaceX, a multivendor marketplace in Vietnam. "
        "Answer briefly (2-5 sentences or a short list). Prices are in Vietnamese dong (₫). "
        "Only recommend products listed below and quote their exact prices; link them as markdown links "
        "like [Product name](/products/123). If something is not in the data, say you don't know. "
        "You cannot place, cancel or refund orders: explain which page to use instead. "
        "Reply in the customer's language (Vietnamese or English).\n\n"
        f"STORE POLICIES\n{_policy_context()}\n\n"
        f"CATALOGUE\n{_products_context(question)}\n\n"
        f"ORDERS\n{_orders_context(customer)}"
    )


def _call_gemini(system: str, contents: list) -> str:
    key = current_app.config.get("GEMINI_API_KEY")
    if not key:
        raise AssistantUnavailable("The assistant is unavailable (no GEMINI_API_KEY configured).")
    body = json.dumps({"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                       "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024,
                                             "thinkingConfig": {"thinkingBudget": 0}}}).encode()
    req = urllib.request.Request(GEMINI_URL.format(model=current_app.config.get("GEMINI_MODEL", "gemini-3.5-flash")),
                                 data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as e:
        current_app.logger.warning("Gemini call failed: %s", e)
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
