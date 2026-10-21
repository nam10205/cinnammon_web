from __future__ import annotations

from ... import clock
from ...errors import InsufficientStock, ValidationError
from ...extensions import db
from ..catalog.models import Product
from .models import Order

SHIPPING_FEE = 30_000
FREE_SHIPPING_FROM = 500_000
STEP_SECONDS = 20
DEMO_CARD = "4242424242424242"


def shipping_fee(subtotal: int) -> int:
    return 0 if subtotal >= FREE_SHIPPING_FROM else SHIPPING_FEE


def checkout(customer, cart: dict[int, int], payment_method: str,
             card_number: str | None = None) -> list[Order]:
    cart = {int(k): int(v) for k, v in (cart or {}).items() if int(v) > 0}
    if not cart:
        raise ValidationError("Your cart is empty")
    if payment_method not in ("cod", "card"):
        raise ValidationError("Choose a payment method")
    if payment_method == "card":
        digits = "".join(ch for ch in (card_number or "") if ch.isdigit())
        if digits != DEMO_CARD:
            raise ValidationError("Card declined — use the demo card 4242 4242 4242 4242")

    products = {p.id: p for p in db.session.query(Product).filter(Product.id.in_(list(cart)))
                .with_for_update().all()}
    for pid in cart:
        if pid not in products:
            raise ValidationError("A product in your cart is no longer available")
    for pid, qty in cart.items():
        p = products[pid]
        if qty > p.stock_quantity:
            raise InsufficientStock(f"Only {p.stock_quantity} left of {p.title}")

    now = clock.now()
    subtotal = sum(qty * products[pid].price for pid, qty in cart.items())
    fee = shipping_fee(subtotal)
    orders = []
    for i, (pid, qty) in enumerate(cart.items()):
        p = products[pid]
        line_fee = fee if i == 0 else 0
        orders.append(Order(
            customer_id=customer.id, product_id=p.id, address_id=customer.address_id,
            quantity=qty, unit_price=p.price, shipping_fee=line_fee,
            total_price=qty * p.price + line_fee, payment_method=payment_method,
            payment_status="paid" if payment_method == "card" else "unpaid",
            status="placed", ordered_at=now))
        p.stock_quantity -= qty
        p.updated_at = now
    db.session.add_all(orders)
    db.session.commit()
    return orders
