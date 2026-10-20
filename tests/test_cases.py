from helpers import delivered_order, disputed_case, paid_order
from marketplacex.modules.audit.models import AuditEvent
from marketplacex.modules.cases import service as cases


def test_case_lifecycle_and_timeline(alice, make_user):
    agent = make_user("admin")
    o = paid_order(alice, "P03", 1)
    c = cases.open_case(alice, o.id, "Where is my order?", "Placed yesterday")
    cases.assign(agent, c.id)
    cases.add_note(agent, c.id, "Seller contacted")
    cases.set_status(agent, c.id, "resolved", "answered")
    assert c.status == "resolved" and c.assignee_id == agent.id
    tl = cases.timeline(agent, c.id)
    assert any("Seller contacted" in t["text"] for t in tl) and any("Confirmed" in t["text"] for t in tl)
    assert AuditEvent.query.filter_by(action="case.view").count() == 1


def test_dispute_decision_via_console(client, alice, login, make_user):
    c = disputed_case(alice)
    login(client, make_user("admin"))
    assert c.reason.encode() in client.get(f"/admin/cases/disputes/{c.id}").data
    client.post(f"/admin/cases/disputes/{c.id}/decide",
                data={"outcome": "refund_customer", "reason_code": "SELLER_FAULT", "note": "photos clear"})
    assert c.status == "refunded"


def test_not_received_dispute(alice, make_user):
    o = delivered_order(alice, "P07")
    cases.report_not_received(alice, o.id, "never arrived")
    assert o.status == "Disputed"
    cases.resolve_order_dispute(make_user("admin"), o.id, True, "CARRIER_LOSS")
    assert o.status == "Refunded"


def test_cases_pages(client, alice, login, make_user):
    paid_order(alice, "P03", 1)
    login(client, alice)
    from marketplacex.modules.order.models import Order
    o = Order.query.first()
    client.post(f"/orders/{o.id}/help", data={"body": "help please"})
    login(client, make_user("admin"))
    html = client.get("/admin/cases/?q=alice").get_data(as_text=True)
    assert "help please" in html or "Alice" in html
    from marketplacex.modules.cases.models import CustomerCase
    assert client.get(f"/admin/cases/cases/{CustomerCase.query.one().id}").status_code == 200


def test_customer_cannot_open_cases_console(client, alice, login):
    login(client, alice)
    assert client.get("/admin/cases/").status_code == 403


def test_order_page_links_to_admin_cases(client, alice, login, make_order):
    o = make_order(status="Delivered")
    login(client, alice)
    html = client.get(f"/orders/{o.id}").get_data(as_text=True)
    assert f"/orders/{o.id}/not-received" in html and "/support" not in html
