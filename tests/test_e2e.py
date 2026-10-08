"""Critical journey from report §14: search -> checkout -> fulfil -> deliver -> review -> return -> refund."""
from helpers import alice_user, offer_id
from marketplacex.modules.checkout.models import CheckoutGroup
from marketplacex.modules.notification.models import Notification
from marketplacex.modules.order.models import Order
from marketplacex.modules.settlement import service as settlement


def _loc(r):
    return r.headers["Location"]


def test_full_customer_journey(client, seeded):
    client.post("/demo-login/customer")
    assert b"Biti" in client.get("/search?q=black+sneakers").data
    client.post("/cart/add", data={"offer_id": offer_id("P03"), "qty": 2})
    alice = alice_user()
    r = client.post("/checkout/quote", data={"address_id": alice.addresses[0].id, "vouchers": "SALE10,SPORT80"},
                    follow_redirects=True)
    assert "1,646,000" in r.get_data(as_text=True)
    g = CheckoutGroup.query.one()
    r = client.post(f"/checkout/{g.id}/place", data={"quote_hash": g.quote_hash, "idempotency_key": "e2e-1"})
    pay_url = _loc(r)
    assert "/payments/" in pay_url
    pid = int(pay_url.split("/")[2])
    client.post(f"/payments/{pid}/simulate/success")
    o = Order.query.one()
    assert o.status == "Confirmed"

    client.get("/logout")
    client.post("/demo-login/seller")
    client.post(f"/seller/orders/{o.id}/accept")
    client.post(f"/seller/orders/{o.id}/pack", data={"weight_g": "800"})
    client.post(f"/seller/orders/{o.id}/handover")
    sid = o.shipments[0].id
    for _ in range(3):
        client.post(f"/logistics/shipments/{sid}/advance")
    assert o.status == "Delivered"

    client.get("/logout")
    client.post("/demo-login/customer")
    client.post(f"/orders/{o.id}/items/{o.items[0].id}/review", data={"rating": "5", "comment": "great"})
    client.post(f"/orders/{o.id}/return", data={f"qty_{o.items[0].id}": "1", "reason": "Damaged item",
                                                "remedy": "refund_only", "statement": "sole cracked"})
    from marketplacex.modules.returns.models import ReturnCase
    case = ReturnCase.query.one()

    client.get("/logout")
    client.post("/demo-login/seller")
    client.post(f"/seller/returns/{case.id}/respond", data={"decision": "accept", "reason": "sorry"})

    client.get("/logout")
    client.post("/demo-login/customer")
    html = client.get(f"/orders/{o.id}").get_data(as_text=True)
    assert "Refunded" in html
    assert Notification.query.filter_by(user_id=alice.id, channel="in_app").count() >= 5
    assert settlement.is_balanced(o.id)


def test_seed_runs_clean(app):
    from marketplacex import seed
    seed.run()
    assert Order.query.count() >= 5
    for o in Order.query.filter(Order.status.in_(["Delivered", "Completed"])).all():
        assert settlement.is_balanced(o.id)
    statuses = {o.status for o in Order.query.all()}
    assert {"Completed", "ReturnRequested", "Shipped", "Confirmed", "Delivered"} <= statuses


def test_all_main_pages_render_after_seed(client, app):
    from marketplacex import seed
    seed.run()
    for role, pages in {"customer": ["/", "/search?q=shoes", "/cart", "/orders", "/saved", "/notifications", "/checkout"],
                        "seller": ["/seller/", "/seller/orders", "/seller/returns", "/seller/settlement"]}.items():
        client.get("/logout")
        client.post(f"/demo-login/{role}")
        for p in pages:
            r = client.get(p)
            assert r.status_code in (200, 302), (role, p, r.status_code)
    client.get("/logout")
    client.post("/demo-login/customer")
    for o in Order.query.filter_by(customer_id=alice_user().id).all():
        assert client.get(f"/orders/{o.id}").status_code == 200
    for o in Order.query.filter(Order.customer_id != alice_user().id).all():
        assert client.get(f"/orders/{o.id}").status_code == 404   # other customers' orders stay private
