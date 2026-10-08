import pytest

from helpers import offer_id, product_id
from marketplacex.errors import PurchaseLimitExceeded, StaleVersion
from marketplacex.modules.cart import service as cart


def test_cart_groups_by_shop_and_versions(alice):
    c = cart.add_item(alice, offer_id("P03"), 2)
    v = c.version
    c = cart.add_item(alice, offer_id("P07"), 1)
    assert c.version == v + 1
    groups = cart.grouped(c)
    assert {g.shop.name for g in groups} == {"SportZone", "TechHub"}
    assert next(g for g in groups if g.shop.name == "SportZone").subtotal_vnd == 1798000


def test_unselected_items_excluded_from_subtotal(alice):
    cart.add_item(alice, offer_id("P03"), 1)
    c = cart.set_selected(alice, offer_id("P03"), False)
    assert cart.grouped(c)[0].subtotal_vnd == 0


def test_stale_version_rejected(alice):
    c = cart.add_item(alice, offer_id("P03"), 1)
    with pytest.raises(StaleVersion):
        cart.change_item(alice, offer_id("P03"), 2, expected_version=c.version - 1)


def test_purchase_limit(alice):
    with pytest.raises(PurchaseLimitExceeded):
        cart.add_item(alice, offer_id("P03"), 6)


def test_qty_zero_removes(alice):
    cart.add_item(alice, offer_id("P03"), 1)
    c = cart.change_item(alice, offer_id("P03"), 0)
    assert c.items == []


@pytest.mark.parametrize("qty", ["0x", "-1", "abc", "6"])          # Review Focus 3 (limit is 5)
def test_bad_qty_flashes_and_keeps_cart(client, alice, login, qty):
    login(client, alice)
    client.post("/cart/add", data={"offer_id": offer_id("P03"), "qty": 1})
    r = client.post(f"/cart/items/{offer_id('P03')}", data={"qty": qty}, follow_redirects=True)
    assert r.status_code == 200 and cart.get_cart(alice).items[0].qty == 1


def test_saved_and_recent(alice):
    assert cart.toggle_saved(alice, "product", product_id("P01")) is True
    cart.record_search(alice, "mouse")
    cart.record_search(alice, "mouse")
    assert len(cart.recent_searches(alice)) == 1
    assert cart.toggle_saved(alice, "product", product_id("P01")) is False


def test_cart_page_renders(client, alice, login):
    login(client, alice)
    client.post("/cart/add", data={"offer_id": offer_id("P03"), "qty": 2})
    html = client.get("/cart").get_data(as_text=True)
    assert "SportZone" in html and "1,798,000" in html
