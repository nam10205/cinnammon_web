import pytest

from helpers import delivered_order, paid_order, seller_user, shipped_order
from marketplacex.errors import IllegalTransition
from marketplacex.modules.admin import policy
from marketplacex.modules.logistics import service as logistics
from marketplacex.modules.seller import service as seller


def test_fulfil_to_delivered(alice):
    o = paid_order(alice, "P03", 1)
    s = seller_user("sportzone@demo")
    seller.accept(s, o.id)
    sh = seller.pack(s, o.id, 800)
    assert o.status == "ReadyToShip" and sh.label_url and sh.weight_g == 800
    seller.hand_over(s, o.id)
    assert o.status == "Shipped"
    while not logistics.has_delivery_event(o.id):
        logistics.advance(sh)
    assert o.status == "Delivered" and o.delivered_at is not None
    assert [e.seq for e in sh.events] == sorted(e.seq for e in sh.events)
    assert sh.events[-1].status == "delivered"


def test_one_active_forward_shipment(alice):
    o = paid_order(alice, "P03", 1)
    s = seller_user("sportzone@demo")
    seller.accept(s, o.id)
    seller.pack(s, o.id, 800)
    from marketplacex.errors import ValidationError
    with pytest.raises((ValidationError, IllegalTransition)):
        seller.pack(s, o.id, 800)


def test_cannot_hand_over_cancelled(alice):
    o = paid_order(alice, "P03", 1)
    s = seller_user("sportzone@demo")
    seller.reject(s, o.id, "out of stock")
    assert o.status == "Cancelled"
    with pytest.raises(IllegalTransition):
        seller.hand_over(s, o.id)


def test_reject_requires_reason(alice):
    from marketplacex.errors import ValidationError
    o = paid_order(alice, "P03", 1)
    with pytest.raises(ValidationError):
        seller.reject(seller_user("sportzone@demo"), o.id, " ")


def test_other_seller_gets_404(client, alice, login):        # Review Focus 1
    o = paid_order(alice, "P03", 1)
    login(client, seller_user("techhub@demo"))
    assert client.post(f"/seller/orders/{o.id}/accept").status_code == 404 and o.status == "Confirmed"
    assert client.get(f"/seller/orders/{o.id}").status_code == 404


def test_delivery_failure_and_reattempt(alice):
    o = shipped_order(alice, "P03")
    logistics.advance(o.shipments[0], fail=True)
    assert o.status == "DeliveryException"
    logistics.reattempt(seller_user("sportzone@demo"), o.shipments[0])
    assert o.status == "Shipped"


def test_pickup_overdue(alice):
    o = paid_order(alice, "P03", 1)
    s = seller_user("sportzone@demo")
    seller.accept(s, o.id)
    sh = seller.pack(s, o.id, 500)
    assert not logistics.pickup_overdue(sh)
    policy.advance_clock(25)
    assert logistics.pickup_overdue(sh)


def test_seller_pages(client, alice, login):
    o = delivered_order(alice, "P03")
    login(client, seller_user("sportzone@demo"))
    assert b"Seller Center" in client.get("/seller/").data
    assert f"#{o.id}".encode() in client.get("/seller/orders").data
    assert client.get(f"/seller/labels/{o.shipments[0].tracking_no}").status_code == 200
