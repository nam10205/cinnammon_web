import pytest

from helpers import alice_user, delivered_order, disputed_case, paid_order
from marketplacex.errors import ValidationError
from marketplacex.modules.audit.models import AuditEvent
from marketplacex.modules.support import service as support


def test_masking_and_reveal_audited(seeded, make_user):
    agent = make_user("support")
    user = support.search(agent, "alice")["customers"][0]
    assert support.mask_email(user.email) == "a***@demo" and support.mask_phone("0912345678") == "******5678"
    with pytest.raises(ValidationError):
        support.reveal(agent, user.id, "email", "")
    assert support.reveal(agent, user.id, "email", "verify identity on call") == "alice@demo"
    assert AuditEvent.query.filter_by(action="pii.reveal").count() == 1


def test_customer_page_masks(client, seeded, login, make_user):
    login(client, make_user("support"))
    html = client.get(f"/support/customers/{alice_user().id}").get_data(as_text=True)
    assert "alice@demo" not in html and "a***@demo" in html


def test_case_lifecycle_and_timeline(alice, make_user):
    agent = make_user("support")
    o = paid_order(alice, "P03", 1)
    c = support.open_case(alice, o.id, "Where is my order?", "Placed yesterday")
    support.assign(agent, c.id)
    support.add_note(agent, c.id, "Seller contacted")
    support.set_status(agent, c.id, "resolved", "answered")
    assert c.status == "resolved" and c.assignee_id == agent.id
    tl = support.timeline(agent, c.id)
    assert any("Seller contacted" in t["text"] for t in tl) and any("Confirmed" in t["text"] for t in tl)
    assert AuditEvent.query.filter_by(action="case.view").count() == 1


def test_dispute_decision_via_console(client, alice, login, make_user):
    c = disputed_case(alice)
    login(client, make_user("support"))
    assert c.reason.encode() in client.get(f"/support/disputes/{c.id}").data
    client.post(f"/support/disputes/{c.id}/decide",
                data={"outcome": "refund_customer", "reason_code": "SELLER_FAULT", "note": "photos clear"})
    assert c.status == "refunded"


def test_not_received_dispute(alice, make_user):
    o = delivered_order(alice, "P07")
    support.report_not_received(alice, o.id, "never arrived")
    assert o.status == "Disputed"
    support.resolve_order_dispute(make_user("support"), o.id, True, "CARRIER_LOSS")
    assert o.status == "Refunded"


def test_support_pages(client, alice, login, make_user):
    paid_order(alice, "P03", 1)
    login(client, alice)
    from marketplacex.modules.order.models import Order
    o = Order.query.first()
    client.post(f"/orders/{o.id}/support", data={"body": "help please"})
    login(client, make_user("support"))
    html = client.get("/support/?q=alice").get_data(as_text=True)
    assert "help please" in html or "Alice" in html
    from marketplacex.modules.support.models import SupportCase
    assert client.get(f"/support/cases/{SupportCase.query.one().id}").status_code == 200
