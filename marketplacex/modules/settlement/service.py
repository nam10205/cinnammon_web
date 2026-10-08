"""Settlement: balanced ledger entries held until the return window closes (BR08, report §12.5)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func

from ...events import subscribe
from ...extensions import db
from ..admin import policy
from ..order import service as order_service
from ..order.models import Order
from .models import LedgerEntry


def _entry(order, account, debit=0, credit=0, group="", memo=""):
    db.session.add(LedgerEntry(order_id=order.id, shop_id=order.shop_id, account=account, debit_vnd=int(debit),
                               credit_vnd=int(credit), status="held", entry_group=group, memo=memo, at=policy.now()))


def post_delivery(order: Order) -> None:
    group = f"order-{order.id}"
    if LedgerEntry.query.filter_by(entry_group=group).first():
        return
    base = order.merchandise_vnd - order.shop_discount_vnd
    fee = base * policy.get_int("platform_fee_pct") // 100
    _entry(order, "customer_payment", debit=order.total_vnd, group=group, memo="Customer payment captured")
    if order.platform_discount_vnd:
        _entry(order, "voucher_funding", debit=order.platform_discount_vnd, group=group, memo="Platform voucher funding")
    _entry(order, "seller_payable", credit=base - fee, group=group, memo="Net payable to seller")
    _entry(order, "platform_fee", credit=fee, group=group, memo=f"Platform fee {policy.get_int('platform_fee_pct')}%")
    _entry(order, "shipping", credit=order.shipping_vnd, group=group, memo="Shipping collected for carrier")
    db.session.flush()


def post_refund(order: Order, amount_vnd: int, ref: str) -> None:
    group = f"refund-{ref}"
    if LedgerEntry.query.filter_by(entry_group=group).first():
        return
    _entry(order, "seller_payable", debit=amount_vnd, group=group, memo="Refund charged to seller payable")
    _entry(order, "refund", credit=amount_vnd, group=group, memo="Refund to customer")
    db.session.flush()


def is_balanced(order_id: int) -> bool:
    d, c = db.session.query(func.coalesce(func.sum(LedgerEntry.debit_vnd), 0),
                            func.coalesce(func.sum(LedgerEntry.credit_vnd), 0)).filter_by(order_id=order_id).one()
    return d == c and d > 0


def release_eligible(actor) -> int:
    from ..returns.models import ReturnCase
    from ..returns.service import OPEN_STATUSES
    limit = policy.now() - timedelta(days=policy.get_int("return_window_days"))
    n = 0
    for o in Order.query.filter(Order.status == "Delivered", Order.delivered_at < limit).all():
        if ReturnCase.query.filter(ReturnCase.order_id == o.id, ReturnCase.status.in_(OPEN_STATUSES)).first():
            continue
        order_service.transition(o, "Completed", actor, "Return window closed; settlement released")
        n += 1
    return n


def statement(shop) -> dict:
    entries = LedgerEntry.query.filter_by(shop_id=shop.id).order_by(LedgerEntry.id.desc()).all()

    def net(account, status=None):
        return sum(e.credit_vnd - e.debit_vnd for e in entries
                   if e.account == account and (status is None or e.status == status))
    return {"held_vnd": net("seller_payable", "held"), "released_vnd": net("seller_payable", "released"),
            "fees_vnd": net("platform_fee"), "refunds_vnd": net("refund"), "entries": entries}


@subscribe("OrderStatusChanged", "settlement")
def _on_status(event) -> None:
    p = event.payload
    order = db.session.get(Order, int(p["order_id"]))
    if p["to"] == "Delivered":
        post_delivery(order)
    elif p["to"] == "Completed":
        for e in LedgerEntry.query.filter_by(order_id=order.id, status="held").all():
            e.status = "released"


@subscribe("PaymentChanged", "settlement")
def _on_refund(event) -> None:
    p = event.payload
    if p.get("kind") != "refund":
        return
    order = None
    if p.get("return_case_id"):
        from ..returns.models import ReturnCase
        case = db.session.get(ReturnCase, int(p["return_case_id"]))
        order = case.order if case else None
    elif p.get("order_id"):
        order = db.session.get(Order, int(p["order_id"]))
    if order is not None and LedgerEntry.query.filter_by(entry_group=f"order-{order.id}").first():
        post_refund(order, int(p["amount_vnd"]), str(p["refund_id"]))
