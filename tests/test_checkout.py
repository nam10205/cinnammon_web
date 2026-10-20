import pytest

from helpers import offer_id, pay_fail, pay_success, shop_id
from marketplacex.errors import QuoteChanged, QuoteExpired
from marketplacex.events import EventLog
from marketplacex.modules.admin import policy
from marketplacex.modules.cart import service as cart
from marketplacex.modules.catalog import service as catalog
from marketplacex.modules.checkout import service as checkout
from marketplacex.modules.inventory import service as inventory
from marketplacex.modules.order import service as order_service
from marketplacex.modules.order.models import Order
from marketplacex.modules.promotion.models import Redemption, Voucher


def quote_two_bitis(alice):
    cart.add_item(alice, offer_id("P03"), 2)
    return checkout.quote(alice, alice.addresses[0].id, ["SALE10", "SPORT80"])


def test_quote_matches_report(alice):        # BR02, report §13.1
    g = quote_two_bitis(alice)
    assert (g.merchandise_vnd, g.discount_vnd, g.shipping_vnd, g.total_vnd) == (1798000, 180000, 28000, 1646000)


def test_place_is_idempotent(alice):
    g = quote_two_bitis(alice)
    checkout.place_order(alice, g.id, "k1", g.quote_hash)
    checkout.place_order(alice, g.id, "k1", g.quote_hash)
    assert inventory.get_ledger(offer_id("P03")).reserved == 2 and Order.query.count() == 1


def test_price_change_detected(alice):
    g = quote_two_bitis(alice)
    catalog.get_offer(offer_id("P03")).price_vnd = 950000
    with pytest.raises(QuoteChanged):
        checkout.place_order(alice, g.id, "k1", g.quote_hash)
    assert inventory.get_ledger(offer_id("P03")).reserved == 0


def test_quote_expiry(alice):
    g = quote_two_bitis(alice)
    policy.advance_clock(1)
    with pytest.raises(QuoteExpired):
        checkout.place_order(alice, g.id, "k1", g.quote_hash)


def test_success_callback_confirms_and_commits(alice):
    g = quote_two_bitis(alice)
    checkout.place_order(alice, g.id, "k1", g.quote_hash)
    pay_success(g.id)
    o = Order.query.one()
    led = inventory.get_ledger(offer_id("P03"))
    assert o.status == "Confirmed" and (led.reserved, led.committed) == (0, 2)
    assert cart.get_cart(alice).items == []
    assert g.status == "completed"
    assert Voucher.query.filter_by(code="SALE10").one().used_count == 1
    assert EventLog.query.filter_by(name="OrderCreated").count() == 1
    assert [i.discount_vnd for i in o.items] == [180000] and o.items[0].title_snapshot.startswith("Biti")


def test_payment_fail_compensates(alice):
    g = quote_two_bitis(alice)
    checkout.place_order(alice, g.id, "k1", g.quote_hash)
    pay_fail(g.id)
    assert Order.query.one().status == "PaymentFailed"
    assert inventory.get_ledger(offer_id("P03")).reserved == 0
    assert Redemption.query.filter_by(status="held").count() == 0
    assert g.status == "failed"


def test_expired_reservation_cancels(alice):
    g = quote_two_bitis(alice)
    checkout.place_order(alice, g.id, "k1", g.quote_hash)
    policy.advance_clock(1)
    checkout.sweep()
    assert Order.query.one().status == "Cancelled"
    assert inventory.get_ledger(offer_id("P03")).reserved == 0


def test_unavailable_item_excluded(alice):  # Review Focus 2
    cart.add_item(alice, offer_id("P03"), 1)
    cart.add_item(alice, offer_id("P07"), 1)
    inventory.set_stock(offer_id("P07"), 0)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    assert [u["offer_id"] for u in g.quote_payload["unavailable"]] == [offer_id("P07")]
    assert g.merchandise_vnd == 899000


def test_two_shops_two_orders_one_group(alice):   # FR11
    cart.add_item(alice, offer_id("P03"), 1)
    cart.add_item(alice, offer_id("P07"), 1)
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, "k", g.quote_hash)
    orders = order_service.orders_of_group(g.id)
    assert {o.shop_id for o in orders} == {shop_id("SportZone"), shop_id("TechHub")}
    assert sum(o.total_vnd for o in orders) == g.total_vnd == 899000 + 429000 + 2 * 28000


def test_checkout_pages(client, alice, login):
    login(client, alice)
    cart.add_item(alice, offer_id("P03"), 2)
    assert client.get("/checkout").status_code == 200
    r = client.post("/checkout/quote", data={"address_id": alice.addresses[0].id, "vouchers": "SALE10, SPORT80"},
                    follow_redirects=True)
    assert "1,646,000" in r.get_data(as_text=True)
    from marketplacex.modules.checkout.models import CheckoutGroup
    g = CheckoutGroup.query.one()
    r = client.post(f"/checkout/{g.id}/place", data={"quote_hash": g.quote_hash, "idempotency_key": "web-1"})
    assert r.status_code == 302 and "/payments/" in r.headers["Location"]


def test_high_value_checkout_is_never_held(alice):
    # 25,000,000 VND exceeds the old risk_max_order_vnd of 20,000,000
    import uuid
    from helpers import offer_id
    from marketplacex.modules.cart import service as cart
    from marketplacex.modules.checkout import service as checkout
    cart.add_item(alice, offer_id("P05"), 4)  # 4 x 6,490,000
    g = checkout.quote(alice, alice.addresses[0].id, [])
    checkout.place_order(alice, g.id, uuid.uuid4().hex, g.quote_hash)
    assert g.status in ("placing", "completed")
