import pytest

from helpers import captured_payment
from marketplacex.errors import InvalidSignature, RefundExceedsCaptured
from marketplacex.events import EventLog
from marketplacex.modules.payment import service as pay


def test_authorize_idempotent_per_attempt(app):
    a = pay.authorize(1, 100000, "att")
    b = pay.authorize(1, 100000, "att")
    assert a.id == b.id and a.status == "pending" and a.provider_ref.startswith("PAY-")


def test_callback_signature_verified(app):
    p = pay.authorize(1, 100000, "att")
    with pytest.raises(InvalidSignature):
        pay.handle_callback({"event_id": "e1", "provider_ref": p.provider_ref, "status": "authorized"}, "bad")


def test_duplicate_callback_single_capture(app):
    p = pay.authorize(1, 100000, "att")
    body = pay.simulate(p.id, "success")
    pay.handle_callback(body["payload"], body["signature"])
    pay.handle_callback(body["payload"], body["signature"])
    assert EventLog.query.filter_by(name="PaymentAuthorized").count() == 1 and p.captured_vnd == 100000
    assert pay.is_captured(1)


def test_late_fail_after_capture_ignored(app):
    p = captured_payment(100000)
    body = pay.simulate(p.id, "fail")
    pay.handle_callback(body["payload"], body["signature"])
    assert p.status == "captured"


def test_refund_bound(app):          # BR07
    p = captured_payment(100000)
    pay.refund(p.id, 60000, "k1")
    pay.refund(p.id, 60000, "k1")          # idempotent
    with pytest.raises(RefundExceedsCaptured):
        pay.refund(p.id, 50000, "k2")
    assert pay.refundable_vnd(p.id) == 40000


def test_callback_endpoint(client, app):
    p = pay.authorize(1, 5000, "att")
    b = pay.simulate(p.id, "fail")
    r = client.post("/payments/callback", json=b["payload"], headers={"X-Signature": b["signature"]})
    assert r.json["status"] == "failed"
    r = client.post("/payments/callback", json=b["payload"], headers={"X-Signature": "nope"})
    assert r.status_code == 400 and r.json["code"] == "invalid_signature"


def test_logistics_quote_flat(seeded):
    from helpers import alice_user, shop_id
    from marketplacex.modules.logistics import service as logistics
    q = logistics.quote(alice_user().addresses[0], [shop_id("SportZone"), shop_id("TechHub")])
    assert q == {shop_id("SportZone"): 28000, shop_id("TechHub"): 28000}
