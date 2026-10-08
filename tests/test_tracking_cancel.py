import pytest

from helpers import offer_id, paid_order, seller_user, user_id
from marketplacex.errors import IllegalTransition
from marketplacex.modules.inventory import service as inventory
from marketplacex.modules.notification.models import Notification
from marketplacex.modules.order import service as order_service
from marketplacex.modules.payment.models import Refund


def test_confirmation_notifies_customer_and_seller(alice):
    paid_order(alice, "P03", 1)
    assert Notification.query.filter_by(user_id=alice.id).count() >= 1
    assert Notification.query.filter_by(user_id=user_id("sportzone@demo")).count() >= 1


def test_cancel_confirmed_refunds_and_restocks(alice):
    o = paid_order(alice, "P03", 1)
    before = inventory.get_ledger(offer_id("P03")).available
    order_service.request_cancel(alice, o, "changed mind")
    assert o.status == "Cancelled" and inventory.get_ledger(offer_id("P03")).available == before + 1
    assert Refund.query.one().amount_vnd == o.total_vnd


def test_cancel_preparing_needs_seller(alice):
    o = paid_order(alice, "P03", 1)
    order_service.transition(o, "Preparing", None)
    order_service.request_cancel(alice, o, "late")
    assert o.status == "CancelRequested"
    order_service.resolve_cancel(seller_user("sportzone@demo"), o, False, "already packed")
    assert o.status == "Preparing"
    order_service.request_cancel(alice, o, "please")
    order_service.resolve_cancel(seller_user("sportzone@demo"), o, True, "ok")
    assert o.status == "Cancelled" and Refund.query.count() == 1


def test_cannot_cancel_shipped(alice):
    o = paid_order(alice, "P03", 1)
    for s in ("Preparing", "ReadyToShip"):
        order_service.transition(o, s, None)
    o.status = "Shipped"
    with pytest.raises(IllegalTransition):
        order_service.request_cancel(alice, o, "too late")


def test_other_customer_gets_404(client, alice, make_user, login):   # Review Focus 1
    o = paid_order(alice, "P03", 1)
    login(client, make_user("customer"))
    assert client.get(f"/orders/{o.id}").status_code == 404
    assert client.post(f"/orders/{o.id}/cancel", data={"reason": "x"}).status_code == 404 and o.status == "Confirmed"


def test_timeline_renders(client, alice, login):
    o = paid_order(alice, "P03", 1)
    login(client, alice)
    html = client.get(f"/orders/{o.id}").get_data(as_text=True)
    assert "PendingPayment" in html and "Confirmed" in html and "Biti" in html
    assert "Biti" in client.get("/orders").get_data(as_text=True)


def test_notification_inbox_and_read(client, alice, login):
    paid_order(alice, "P03", 1)
    login(client, alice)
    n = Notification.query.filter_by(user_id=alice.id).first()
    assert n.body in client.get("/notifications").get_data(as_text=True)
    client.post(f"/notifications/{n.id}/read")
    assert n.read_at is not None
