import pytest
from marketplacex.errors import InsufficientStock, ValidationError
from marketplacex.modules.order import service
from marketplacex.modules.order.models import Order

def test_shipping_fee_threshold():
    assert service.shipping_fee(499_999) == 30_000
    assert service.shipping_fee(500_000) == 0

def test_cart_caps_at_stock_and_refuses_out_of_stock(client, demo):
    client.post("/cart/add", data={"product_id": demo.galaxy.id, "qty": 10})
    with client.session_transaction() as s:
        assert s["cart"] == {str(demo.galaxy.id): 3}
    r = client.post("/cart/add", data={"product_id": demo.cheap.id, "qty": 1}, follow_redirects=True)
    assert "Bookmark is out of stock" in r.get_data(as_text=True)

def test_multi_line_card_checkout(demo, clock):
    orders = service.checkout(demo.alice, {demo.book.id: 2, demo.iphone.id: 1}, "card", "4242 4242 4242 4242")
    assert [(o.quantity, o.unit_price, o.shipping_fee, o.total_price) for o in orders] == [
        (2, 100_000, 0, 200_000), (1, 20_000_000, 0, 20_000_000)]
    assert {o.ordered_at for o in orders} == {clock.now}
    assert all(o.status == "placed" and o.payment_status == "paid" and o.address_id == demo.alice.address_id for o in orders)
    assert demo.book.stock_quantity == 48 and demo.iphone.stock_quantity == 4

def test_small_cod_order_pays_shipping_on_first_row(demo):
    (o,) = service.checkout(demo.alice, {demo.book.id: 1}, "cod")
    assert (o.shipping_fee, o.total_price, o.payment_status) == (30_000, 130_000, "unpaid")

def test_declined_card_writes_nothing(demo):
    with pytest.raises(ValidationError, match="Card declined"):
        service.checkout(demo.alice, {demo.book.id: 1}, "card", "4000 0000 0000 0002")
    assert Order.query.count() == 0 and demo.book.stock_quantity == 50

def test_stock_shortfall_aborts_whole_cart(demo):
    demo.galaxy.stock_quantity = 1
    with pytest.raises(InsufficientStock, match="Only 1 left of Samsung Galaxy S24"):
        service.checkout(demo.alice, {demo.book.id: 1, demo.galaxy.id: 2}, "cod")
    assert Order.query.count() == 0 and demo.book.stock_quantity == 50

def test_checkout_route_clears_cart_and_double_submit_is_refused(client, demo, login_as):
    login_as(client, "customer", demo.alice)
    client.post("/cart/add", data={"product_id": demo.book.id, "qty": 1})
    client.post("/checkout", data={"payment_method": "cod"})
    assert Order.query.count() == 1
    r = client.post("/checkout", data={"payment_method": "cod"}, follow_redirects=True)
    assert "Your cart is empty" in r.get_data(as_text=True) and Order.query.count() == 1

def test_visitor_checkout_redirects_to_login(client, demo):
    r = client.post("/checkout", data={"payment_method": "cod"})
    assert r.status_code == 302 and "/login" in r.headers["Location"]

def test_cart_and_checkout_pages_render(client, demo, login_as):
    login_as(client, "customer", demo.alice)
    client.post("/cart/add", data={"product_id": demo.book.id, "qty": 2})
    assert "Sách Đắc Nhân Tâm" in client.get("/cart").get_data(as_text=True)
    assert "4242" in client.get("/checkout").get_data(as_text=True)

def test_visitor_cart_survives_quick_login(client, demo):
    client.post("/cart/add", data={"product_id": demo.book.id, "qty": 1})
    assert "/cart" in client.get("/").get_data(as_text=True)
    client.post("/login/quick/customer")
    with client.session_transaction() as s:
        assert s["cart"] == {str(demo.book.id): 1}
    assert "Sách Đắc Nhân Tâm" in client.get("/checkout").get_data(as_text=True)

def test_sold_out_line_is_pruned_and_does_not_block_checkout(client, demo, login_as):
    from marketplacex.extensions import db
    login_as(client, "customer", demo.alice)
    client.post("/cart/add", data={"product_id": demo.galaxy.id, "qty": 1})
    client.post("/cart/add", data={"product_id": demo.book.id, "qty": 1})
    demo.galaxy.stock_quantity = 0
    db.session.commit()
    client.get("/cart")
    with client.session_transaction() as s:
        assert str(demo.galaxy.id) not in s["cart"]
    client.post("/checkout", data={"payment_method": "cod"})
    assert Order.query.count() == 1

def test_checkout_post_prunes_and_flashes(client, demo, login_as):
    from marketplacex.extensions import db
    login_as(client, "customer", demo.alice)
    client.post("/cart/add", data={"product_id": demo.galaxy.id, "qty": 1})
    client.post("/cart/add", data={"product_id": demo.book.id, "qty": 1})
    demo.galaxy.stock_quantity = 0
    db.session.commit()
    r = client.post("/checkout", data={"payment_method": "cod"}, follow_redirects=True)
    assert "no longer available and were removed" in r.get_data(as_text=True)
    assert [o.product_id for o in Order.query.all()] == [demo.book.id]

def test_duplicate_checkout_within_window_is_refused(demo, clock):
    service.checkout(demo.alice, {demo.book.id: 1}, "cod")
    with pytest.raises(ValidationError, match="just placed"):
        service.checkout(demo.alice, {demo.book.id: 1}, "cod")
    assert Order.query.count() == 1
    clock.advance(6)
    service.checkout(demo.alice, {demo.book.id: 1}, "cod")
    assert Order.query.count() == 2
