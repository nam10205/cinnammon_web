"""Regression tests for the final-review findings."""
import pytest

from helpers import _owner_of, delivered_order, offer_id, pay_success, shop_id
from marketplacex.errors import RefundExceedsCaptured, ValidationError
from marketplacex.modules.cart import service as cart
from marketplacex.modules.checkout import service as checkout
from marketplacex.modules.inventory import service as inventory
from marketplacex.modules.order import service as order_service
from marketplacex.modules.payment import service as payment
from marketplacex.modules.payment.models import Refund
from marketplacex.modules.returns import service as returns


def _two_shop_checkout(alice):
    cart.add_item(alice, offer_id("P03"), 1)
    cart.add_item(alice, offer_id("P07"), 1)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    return g, order_service.orders_of_group(g.id)


def test_cancel_one_shop_order_then_pay(alice):            # Critical 1
    g, (o1, o2) = _two_shop_checkout(alice)
    cancelled, kept = (o1, o2) if o1.shop_id == shop_id("TechHub") else (o2, o1)
    order_service.request_cancel(alice, cancelled, "changed mind")
    pay_success(g.id)
    assert kept.status == "Confirmed" and cancelled.status == "Cancelled" and g.status == "completed"
    assert Refund.query.one().amount_vnd == cancelled.total_vnd
    p03, p07 = inventory.get_ledger(offer_id("P03")), inventory.get_ledger(offer_id("P07"))
    assert (p03.reserved, p03.committed) == (0, 1)
    assert (p07.available, p07.reserved, p07.committed) == (50, 0, 0)


def test_cancel_only_order_while_pending_fails_group(alice):
    cart.add_item(alice, offer_id("P03"), 1)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    order_service.request_cancel(alice, order_service.orders_of_group(g.id)[0], "oops")
    assert g.status == "failed" and payment.latest_for_group(g.id).status == "voided"


def test_partial_dispute_capped_to_order(alice, make_user):  # Important 2
    from marketplacex.modules.logistics import service as logistics
    from marketplacex.modules.seller import service as seller
    cart.add_item(alice, offer_id("P11"), 1)
    cart.add_item(alice, offer_id("P05"), 1)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    pay_success(g.id)
    o = next(x for x in order_service.orders_of_group(g.id) if x.shop_id == shop_id("StyleHouse"))
    s = _owner_of(o)
    seller.accept(s, o.id)
    sh = seller.pack(s, o.id, 300)
    seller.hand_over(s, o.id)
    while o.status != "Delivered":
        logistics.advance(sh)
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    returns.seller_respond(s, c.id, "reject", "no")
    returns.escalate(alice, c.id, "please")
    with pytest.raises((ValidationError, RefundExceedsCaptured)):
        returns.decide_dispute(make_user("support"), c.id, "partial", "GOODWILL", 3_000_000, "")
    assert Refund.query.count() == 0


def test_second_case_refund_after_first_rejected(alice, make_user):   # Important 3
    from marketplacex.modules.logistics import service as logistics
    from marketplacex.modules.seller import service as seller
    cart.add_item(alice, offer_id("P03"), 1)
    cart.add_item(alice, offer_id("P08"), 1)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    pay_success(g.id)
    o = order_service.orders_of_group(g.id)[0]
    s = _owner_of(o)
    seller.accept(s, o.id)
    sh = seller.pack(s, o.id, 900)
    seller.hand_over(s, o.id)
    while o.status != "Delivered":
        logistics.advance(sh)
    c1 = returns.open_case(alice, o.id, {o.items[0].id: 1}, "r1", "refund_only", "s1")
    c2 = returns.open_case(alice, o.id, {o.items[1].id: 1}, "r2", "refund_only", "s2")
    returns.seller_respond(s, c1.id, "reject", "no")
    returns.escalate(alice, c1.id, "please")
    returns.decide_dispute(make_user("support"), c1.id, "side_with_seller", "EVIDENCE_INSUFFICIENT", None, "")
    assert o.status == "ReturnRequested"          # c2 still open
    returns.seller_respond(s, c2.id, "accept", "ok")
    assert c2.status == "refunded" and o.status == "Refunded"
