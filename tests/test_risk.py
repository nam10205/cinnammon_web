from helpers import delivered_order, offer_id, seller_user
from marketplacex.modules.admin import policy
from marketplacex.modules.cart import service as cart
from marketplacex.modules.checkout import service as checkout
from marketplacex.modules.inventory import service as inventory
from marketplacex.modules.payment.models import PaymentAttempt
from marketplacex.modules.returns import service as returns
from marketplacex.modules.risk import service as risk
from marketplacex.modules.risk.models import RiskAlert


def _big_checkout(alice):
    cart.add_item(alice, offer_id("P05"), 4)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    return g


def test_high_value_checkout_held_then_released(alice, make_user):
    g = _big_checkout(alice)
    a = RiskAlert.query.one()
    assert a.rule == "HIGH_VALUE" and g.status == "placing" and a.status == "held"
    assert PaymentAttempt.query.count() == 0
    risk.release(make_user("risk"), a.id, "customer verified by phone")
    assert PaymentAttempt.query.count() == 1 and a.status == "released"


def test_reject_compensates(alice, make_user):
    g = _big_checkout(alice)
    risk.reject(make_user("risk"), RiskAlert.query.one().id, "stolen card pattern")
    assert inventory.get_ledger(offer_id("P05")).reserved == 0 and g.status == "failed"


def test_normal_checkout_approved(alice):
    cart.add_item(alice, offer_id("P03"), 1)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    assert RiskAlert.query.count() == 0 and PaymentAttempt.query.count() == 1


def test_refund_velocity_holds(alice, monkeypatch, make_user):
    real = policy.get_int
    monkeypatch.setattr(policy, "get_int", lambda k: 0 if k == "risk_max_refunds_30d" else real(k))
    o = delivered_order(alice, "P03")
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "accept", "ok")
    assert c.status == "refund_pending" and RiskAlert.query.filter_by(target_type="refund").count() == 1
    risk.release(make_user("risk"), RiskAlert.query.filter_by(target_type="refund").one().id, "legit")
    assert c.status == "refunded"


def test_reason_required(alice, make_user):
    import pytest
    from marketplacex.errors import ValidationError
    _big_checkout(alice)
    with pytest.raises(ValidationError):
        risk.release(make_user("risk"), RiskAlert.query.one().id, "")


def test_risk_pages(client, alice, login, make_user):
    _big_checkout(alice)
    login(client, make_user("risk"))
    assert b"HIGH_VALUE" in client.get("/risk/").data
    assert client.get(f"/risk/alerts/{RiskAlert.query.one().id}").status_code == 200
