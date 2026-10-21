from datetime import timedelta
import pytest
from marketplacex.errors import IllegalTransition
from marketplacex.modules.order import service

def _order(demo, method="cod", qty=1):
    return service.checkout(demo.alice, {demo.book.id: qty}, method, "4242424242424242" if method == "card" else None)[0]

def test_steps_advance_on_time(demo, clock):
    o = _order(demo)
    clock.advance(19); service.advance_due(); assert o.status == "placed"
    clock.advance(1);  service.advance_due(); assert o.status == "processing"
    clock.advance(20); service.advance_due(); assert o.status == "shipped" and o.shipped_at == o.ordered_at + timedelta(seconds=40)
    clock.advance(20); service.advance_due(); assert o.status == "delivered" and o.payment_status == "paid"

def test_unwatched_order_stamps_due_times_not_read_time(demo, clock):
    o = _order(demo)
    clock.advance(3600)
    assert service.advance_due() == 1
    assert o.status == "delivered"
    assert o.shipped_at == o.ordered_at + timedelta(seconds=40)
    assert o.delivered_at == o.ordered_at + timedelta(seconds=60)

def test_cancel_window_restores_stock_and_refunds(demo, clock):
    o = _order(demo, "card", qty=2)
    clock.advance(25)
    service.cancel(o)
    assert (o.status, o.payment_status, demo.book.stock_quantity) == ("cancelled", "refunded", 50)
    o2 = _order(demo)
    clock.advance(40)
    with pytest.raises(IllegalTransition):
        service.cancel(o2)

def test_skip_step(demo, clock):
    o = _order(demo)
    clock.advance(5)
    service.skip_step(o); service.skip_step(o)
    assert o.status == "shipped" and o.shipped_at == clock.now
    service.skip_step(o)
    assert o.status == "delivered" and o.payment_status == "paid"
    with pytest.raises(IllegalTransition):
        service.skip_step(o)

def test_my_orders_groups_by_checkout(demo, clock):
    service.checkout(demo.alice, {demo.book.id: 1, demo.galaxy.id: 1}, "cod")
    clock.advance(100)
    service.checkout(demo.alice, {demo.book.id: 1}, "cod")
    groups = service.orders_for_customer(demo.alice)
    assert [len(g) for g in groups] == [1, 2]

def test_other_customers_order_is_404(client, demo, login_as):
    o = _order(demo)
    login_as(client, "customer", demo.binh)
    assert client.get(f"/orders/{o.id}").status_code == 404
    assert client.post(f"/orders/{o.id}/cancel").status_code == 404

def test_progress_json(client, demo, clock, login_as):
    o = _order(demo)
    login_as(client, "customer", demo.alice)
    clock.advance(45)
    data = client.get(f"/orders/{o.id}/progress").get_json()
    assert data["status"] == "shipped"
    assert [s["done"] for s in data["steps"]] == [True, True, True, False]

def test_pages_render_and_cancel_route(client, demo, clock, login_as):
    o = _order(demo)
    login_as(client, "customer", demo.alice)
    assert client.get("/orders").status_code == 200
    assert b"data-progress-url" in client.get(f"/orders/{o.id}").data
    assert client.post(f"/orders/{o.id}/cancel").status_code == 302
    assert o.status == "cancelled"
