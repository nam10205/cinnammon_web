import pytest

from marketplacex.errors import IllegalTransition
from marketplacex.events import EventLog
from marketplacex.modules.admin import policy
from marketplacex.modules.audit.models import AuditEvent
from marketplacex.modules.order import service as order_service
from marketplacex.modules.order.models import OrderStatusHistory
from marketplacex.modules.order.state_machine import TRANSITIONS

LEGAL = [("Draft", "PendingPayment"), ("PendingPayment", "Cancelled"), ("Confirmed", "Preparing"),
         ("Preparing", "ReadyToShip"), ("Preparing", "CancelRequested"), ("Delivered", "Completed"),
         ("Shipped", "DeliveryException"), ("ReturnRequested", "Refunded")]
ILLEGAL = [("PendingPayment", "Shipped"), ("Cancelled", "Confirmed"), ("Draft", "Delivered"), ("Shipped", "Preparing"),
           ("Refunded", "Completed")]


@pytest.mark.parametrize("a,b", LEGAL)
def test_legal(app, a, b):
    assert b in TRANSITIONS[a]


@pytest.mark.parametrize("a,b", ILLEGAL)
def test_illegal_raises(make_order, a, b):
    o = make_order(status=a)
    with pytest.raises(IllegalTransition):
        order_service.transition(o, b, None)
    assert o.status == a


def test_transition_writes_history_audit_event(make_order):
    o = make_order(status="Confirmed")
    order_service.transition(o, "Preparing", None, "seller accepted")
    h = OrderStatusHistory.query.filter_by(order_id=o.id).one()
    assert (h.from_status, h.to_status, h.reason) == ("Confirmed", "Preparing", "seller accepted")
    assert EventLog.query.filter_by(name="OrderStatusChanged").count() == 1
    assert AuditEvent.query.filter_by(action="order.Preparing").count() == 1
    assert o.version == 2


def test_guard_blocks_unpaid_confirm(make_order, monkeypatch):
    monkeypatch.setattr("marketplacex.modules.order.state_machine._is_captured", lambda gid: False)
    with pytest.raises(IllegalTransition, match="paymentAuthorized"):
        order_service.transition(make_order(status="PendingPayment"), "Confirmed", None)


def test_guard_allows_paid_confirm(make_order, monkeypatch):
    monkeypatch.setattr("marketplacex.modules.order.state_machine._is_captured", lambda gid: True)
    o = order_service.transition(make_order(status="PendingPayment"), "Confirmed", None)
    assert o.status == "Confirmed"


def test_delivery_guard(make_order, monkeypatch):
    monkeypatch.setattr("marketplacex.modules.order.state_machine._has_delivery", lambda oid: False)
    with pytest.raises(IllegalTransition, match="deliveryEvidenceValid"):
        order_service.transition(make_order(status="Shipped"), "Delivered", None)


def test_return_window_guard(make_order):
    o = make_order(status="Delivered")
    o.delivered_at = policy.now()
    policy.advance_clock(8 * 24)
    with pytest.raises(IllegalTransition, match="withinReturnWindow"):
        order_service.transition(o, "ReturnRequested", None)


def test_cancel_requested_remembers_previous(make_order):
    o = make_order(status="ReadyToShip")
    order_service.transition(o, "CancelRequested", None, "customer asked")
    assert o.cancel_from == "ReadyToShip"
    order_service.transition(o, "ReadyToShip", None, "seller declined")
    assert o.status == "ReadyToShip"


def test_customer_ownership(make_order, make_user):
    from marketplacex.errors import NotFound
    o = make_order(status="Confirmed")
    with pytest.raises(NotFound):
        order_service.get_for_customer(make_user("customer"), o.id)
