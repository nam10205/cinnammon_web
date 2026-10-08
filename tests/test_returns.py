import io

import pytest
from werkzeug.datastructures import FileStorage

from helpers import c_return_shipment, delivered_order, offer_id, paid_order, seller_user
from marketplacex.errors import NotEligible, ValidationError
from marketplacex.modules.admin import policy
from marketplacex.modules.inventory import service as inventory
from marketplacex.modules.logistics import service as logistics
from marketplacex.modules.payment.models import Refund
from marketplacex.modules.returns import service as returns


def test_eligibility_reasons(alice):
    o = paid_order(alice, "P03", 1)
    with pytest.raises(NotEligible, match="not delivered"):
        returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    o2 = delivered_order(alice, "P03")
    with pytest.raises(NotEligible, match="Quantity"):
        returns.open_case(alice, o2.id, {o2.items[0].id: 9}, "r", "refund_only", "s")
    policy.advance_clock(8 * 24)
    with pytest.raises(NotEligible, match="window"):
        returns.open_case(alice, o2.id, {o2.items[0].id: 1}, "r", "refund_only", "s")


def test_no_duplicate_open_case(alice):
    o = delivered_order(alice, "P03", 2)
    returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    with pytest.raises(NotEligible, match="open case"):
        returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")


def test_refund_only_accept(alice):
    o = delivered_order(alice, "P03")
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "broken", "refund_only", "sole broke")
    assert o.status == "ReturnRequested" and c.seller_deadline is not None
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "accept", "sorry")
    assert c.status == "refunded" and o.status == "Refunded" and c.refund_amount_vnd == returns.refund_amount(c)
    assert c.refund_amount_vnd == 899000 + 28000      # full return includes shipping


def test_partial_quantity_refund_amount(alice):
    o = delivered_order(alice, "P03", 2)
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "one broke", "refund_only", "s")
    assert returns.refund_amount(c) == 899000


def test_return_shipment_inspection(alice):
    o = delivered_order(alice, "P03")
    s = seller_user("sportzone@demo")
    before = inventory.get_ledger(offer_id("P03")).available
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "size", "return_and_refund", "too small")
    returns.seller_respond(s, c.id, "accept", "ok")
    assert c.status == "awaiting_return"
    sh = c_return_shipment(c)
    while c.status != "inspecting":
        logistics.advance(sh)
    returns.inspect(s, c.id, True, "fine")
    assert c.status == "refunded" and o.status == "Refunded"
    assert inventory.get_ledger(offer_id("P03")).available == before + 1


def test_propose_then_accept(alice):
    o = delivered_order(alice, "P03")
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "scratch", "refund_only", "small scratch")
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "propose", "partial refund", 200000)
    assert c.status == "proposed"
    returns.accept_proposal(alice, c.id)
    assert c.status == "refunded" and Refund.query.one().amount_vnd == 200000


def test_reject_escalate_decide(alice, make_user):
    o = delivered_order(alice, "P03")
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "fake", "refund_only", "not genuine")
    with pytest.raises(NotEligible):
        returns.escalate(alice, c.id, "too early")
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "reject", "item is genuine")
    returns.escalate(alice, c.id, "photos attached")
    assert c.status == "disputed"
    returns.decide_dispute(make_user("support"), c.id, "side_with_seller", "EVIDENCE_INSUFFICIENT", None, "")
    assert c.status == "closed" and o.status == "Rejected"
    with pytest.raises(NotEligible):
        returns.decide_dispute(make_user("support"), c.id, "refund_customer", "X", None, "")


def test_deadline_allows_escalation(alice):
    o = delivered_order(alice, "P03")
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "late", "refund_only", "s")
    policy.advance_clock(49)
    assert returns.can_escalate(c)


@pytest.mark.parametrize("data,ok", [(b"\x89PNG\r\n\x1a\n" + b"0" * 10, True), (b"MZ\x90\x00", False),
                                     (b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024 + 1), False)])
def test_evidence_upload_validation(app, data, ok):          # Review Focus 5
    f = FileStorage(stream=io.BytesIO(data), filename="e.png")
    if ok:
        assert returns.save_evidence_image(f).startswith("/static/uploads/")
    else:
        with pytest.raises(ValidationError):
            returns.save_evidence_image(f)


def test_return_pages(client, alice, login):
    o = delivered_order(alice, "P03")
    login(client, alice)
    assert client.get(f"/orders/{o.id}/return").status_code == 200
    client.post(f"/orders/{o.id}/return", data={f"qty_{o.items[0].id}": "1", "reason": "broken", "remedy": "refund_only",
                                                "statement": "it broke"})
    c = returns.cases_for_order(o.id)[0]
    assert "it broke" in client.get(f"/returns/{c.id}").get_data(as_text=True)
    login(client, seller_user("sportzone@demo"))
    assert b"broken" in client.get("/seller/returns").data
