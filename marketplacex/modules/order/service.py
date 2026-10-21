from __future__ import annotations

from datetime import timedelta

from ... import clock
from ...errors import IllegalTransition, InsufficientStock, NotFound, ValidationError
from ...extensions import db
from ..catalog.models import Product
from .models import Order

SHIPPING_FEE = 30_000
FREE_SHIPPING_FROM = 500_000
STEP_SECONDS = 20
DEMO_CARD = "4242424242424242"
DUPLICATE_WINDOW_SECONDS = 5


# Every courier has its own fee, so the stored shippingFee alone says which one carried
# the order (no extra column). Only Vinfast keeps the free-shipping threshold.
DELIVERIES = {
    "vinbot": {"name": "Vinbot", "blurb": "Sidewalk robot, rolls to your door", "fee": 15_000, "icon": "robot"},
    "vinno": {"name": "Vinno", "blurb": "Electric scooter through the alleys", "fee": 25_000, "icon": "scooter"},
    "vinfast": {"name": "Vinfast", "blurb": "Electric car, free from 500,000 ₫", "fee": SHIPPING_FEE, "icon": "car-front-fill"},
    "vindrone": {"name": "Vindrone", "blurb": "Quadcopter, straight over the rooftops", "fee": 65_000, "icon": "fan"},
    "vinsubmarine": {"name": "Vinsubmarine", "blurb": "Up the river, quietly", "fee": 150_000, "icon": "water"},
    "vinair": {"name": "Vinair", "blurb": "Private jet, for the impatient", "fee": 290_000, "icon": "airplane-fill"},
}
DEFAULT_DELIVERY = "vinfast"


def shipping_fee(subtotal: int, delivery: str = DEFAULT_DELIVERY) -> int:
    if delivery == DEFAULT_DELIVERY and subtotal >= FREE_SHIPPING_FROM:
        return 0
    return DELIVERIES[delivery]["fee"]


def delivery_of(order) -> str:
    """The courier for an order, read back from the fee its checkout paid."""
    fee = (db.session.query(db.func.coalesce(db.func.sum(Order.shipping_fee), 0))
           .filter(Order.customer_id == order.customer_id, Order.ordered_at == order.ordered_at).scalar())
    return next((k for k, d in DELIVERIES.items() if d["fee"] == fee), DEFAULT_DELIVERY)


def checkout(customer, cart: dict[int, int], payment_method: str,
             card_number: str | None = None, delivery: str = DEFAULT_DELIVERY) -> list[Order]:
    cart = {int(k): int(v) for k, v in (cart or {}).items() if int(v) > 0}
    if not cart:
        raise ValidationError("Your cart is empty")
    if payment_method not in ("cod", "card"):
        raise ValidationError("Choose a payment method")
    if delivery not in DELIVERIES:
        raise ValidationError("Choose a delivery option")
    if payment_method == "card":
        digits = "".join(ch for ch in (card_number or "") if ch.isdigit())
        if digits != DEMO_CARD:
            raise ValidationError("Card declined — use the demo card 4242 4242 4242 4242")

    recent_from = clock.now() - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    recent: dict = {}
    for o in db.session.query(Order).filter(Order.customer_id == customer.id,
                                            Order.ordered_at >= recent_from).all():
        recent.setdefault(o.ordered_at, set()).add((o.product_id, o.quantity))
    if set(cart.items()) in recent.values():
        raise ValidationError("This order was just placed — check My orders")

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
    fee = shipping_fee(subtotal, delivery)
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


STEPS = ("placed", "processing", "shipped", "delivered")
_ACTIVE = ("placed", "processing", "shipped")


def _deliver(order, at) -> None:
    order.status = "delivered"
    order.delivered_at = at
    if order.payment_method == "cod" and order.payment_status == "unpaid":
        order.payment_status = "paid"


def advance_due() -> int:
    now = clock.now()
    step = timedelta(seconds=STEP_SECONDS)
    changed = 0
    for o in db.session.query(Order).filter(Order.status.in_(_ACTIVE)).all():
        moved = False
        while True:
            if o.status == "placed" and now >= o.ordered_at + step:
                o.status = "processing"
            elif o.status == "processing" and now >= o.ordered_at + 2 * step:
                o.status = "shipped"
                o.shipped_at = o.ordered_at + 2 * step
            elif o.status == "shipped" and now >= o.shipped_at + step:
                _deliver(o, o.shipped_at + step)
            else:
                break
            moved = True
        changed += moved
    db.session.commit()
    return changed


def skip_step(order) -> None:
    now = clock.now()
    if order.status == "placed":
        order.status = "processing"
    elif order.status == "processing":
        order.status = "shipped"
        order.shipped_at = now
    elif order.status == "shipped":
        _deliver(order, now)
    else:
        raise IllegalTransition(f"Order is already {order.status}")
    db.session.commit()


def cancel(order) -> None:
    advance_due()
    if order.status not in ("placed", "processing"):
        raise IllegalTransition("Only orders that have not shipped can be cancelled")
    order.product.stock_quantity += order.quantity
    order.product.updated_at = clock.now()
    if order.payment_status == "paid":
        order.payment_status = "refunded"
    order.status = "cancelled"
    db.session.commit()


def orders_for_customer(customer) -> list[list[Order]]:
    advance_due()
    rows = (db.session.query(Order).filter(Order.customer_id == customer.id)
            .order_by(Order.ordered_at.desc(), Order.id).all())
    groups: list[list[Order]] = []
    for o in rows:
        if groups and groups[-1][0].ordered_at == o.ordered_at:
            groups[-1].append(o)
        else:
            groups.append([o])
    return groups


def get_order(order_id: int) -> Order:
    o = db.session.get(Order, order_id)
    if o is None:
        raise NotFound("Order not found")
    return o


def progress(order) -> dict:
    step = timedelta(seconds=STEP_SECONDS)
    iso = lambda d: d.isoformat() if d else None
    if order.status == "cancelled":
        done = {"placed"}
    else:
        done = set(STEPS[:STEPS.index(order.status) + 1])
    at = {"placed": order.ordered_at, "processing": order.ordered_at + step,
          "shipped": order.shipped_at, "delivered": order.delivered_at}
    return {"status": order.status, "payment_status": order.payment_status,
            "steps": [{"name": n, "done": n in done, "at": iso(at[n]) if n in done else None}
                      for n in STEPS]}
