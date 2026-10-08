"""Order aggregate: the only place where order status changes (BR05)."""
from __future__ import annotations

from ...errors import IllegalTransition, NotFound
from ...events import publish
from ...extensions import db
from ..admin import policy
from ..audit import service as audit
from . import state_machine
from .models import Order, OrderItem, OrderStatusHistory


def create_orders(group, shop_lines: list[dict], address, actor) -> list[Order]:
    orders = []
    for line in shop_lines:
        o = Order(group_id=group.id, attempt_id=group.attempt_id, shop_id=line["shop_id"],
                  customer_id=group.customer_id, address_snapshot=address.as_dict(), status="Draft",
                  merchandise_vnd=line["merchandise_vnd"], discount_vnd=line["discount_vnd"],
                  shop_discount_vnd=line.get("shop_discount_vnd", 0),
                  platform_discount_vnd=line.get("platform_discount_vnd", 0),
                  shipping_vnd=line["shipping_vnd"], total_vnd=line["total_vnd"], created_at=policy.now())
        for it in line["items"]:
            o.items.append(OrderItem(offer_id=it["offer_id"], title_snapshot=it["title"], variant_snapshot=it["variant"],
                                     unit_price_vnd=it["unit_price_vnd"], qty=it["qty"], discount_vnd=it["discount_vnd"]))
        db.session.add(o)
        db.session.flush()
        db.session.add(OrderStatusHistory(order_id=o.id, from_status=None, to_status="Draft",
                                          actor_id=getattr(actor, "id", None), reason="Checkout attempt", at=policy.now()))
        orders.append(o)
    for o in orders:
        transition(o, "PendingPayment", actor, "Stock and vouchers reserved")
    db.session.commit()
    return orders


def transition(order: Order, to: str, actor, reason: str | None = None) -> Order:
    ok, why = state_machine.check(order, to)
    if not ok:
        raise IllegalTransition(why)
    frm = order.status
    if to == "CancelRequested":
        order.cancel_from = frm
    if to == "Delivered":
        order.delivered_at = policy.now()
    order.status = to
    order.version += 1
    db.session.add(OrderStatusHistory(order_id=order.id, from_status=frm, to_status=to,
                                      actor_id=getattr(actor, "id", None), reason=reason, at=policy.now()))
    audit.record(actor, f"order.{to}", "order", order.id, reason, {"status": frm}, {"status": to})
    # Entry action: publish the status change; notification and settlement subscribe to it.
    publish("OrderStatusChanged", order.id, {"order_id": order.id, "from": frm, "to": to, "shop_id": order.shop_id,
                                             "customer_id": order.customer_id, "reason": reason,
                                             "actor_role": getattr(actor, "role", "system")})
    db.session.commit()
    return order


def get_order(order_id: int) -> Order:
    o = db.session.get(Order, order_id)
    if o is None:
        raise NotFound("Order not found")
    return o


def get_for_customer(customer, order_id: int) -> Order:
    o = db.session.get(Order, order_id)
    if o is None or o.customer_id != customer.id:
        raise NotFound("Order not found")
    return o


def get_for_shop_owner(user, order_id: int) -> Order:
    o = db.session.get(Order, order_id)
    if o is None or o.shop.owner_id != user.id:
        raise NotFound("Order not found")
    return o


def orders_of_customer(customer) -> list[Order]:
    return Order.query.filter_by(customer_id=customer.id).order_by(Order.id.desc()).all()


def orders_of_shop(shop, status: str | None = None) -> list[Order]:
    q = Order.query.filter_by(shop_id=shop.id)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(Order.id.desc()).all()


def orders_of_group(group_id: int) -> list[Order]:
    return Order.query.filter_by(group_id=group_id).order_by(Order.id).all()
