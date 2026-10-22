def test_table_counts(demo):
    from marketplacex.modules.admin import service
    counts = dict(service.table_counts())
    assert list(counts) == ["FullName", "Address", "Customer", "SearchHistory", "Category", "Product", "ProductImage", "Order"]
    assert counts["Customer"] == 2 and counts["Product"] == 4 and counts["Order"] == 0

def test_admin_access(client, demo, login_as):
    assert client.get("/admin").status_code == 302
    login_as(client, "seller")
    assert client.get("/admin").status_code == 403
    login_as(client, "admin")
    assert "ProductImage" in client.get("/admin").get_data(as_text=True)

def test_category_delete_refused_when_not_empty(client, demo, login_as):
    from marketplacex.modules.catalog.models import Category
    login_as(client, "admin")
    r = client.post(f"/admin/categories/{demo.books.id}/delete", follow_redirects=True)
    assert "Category still has products" in r.get_data(as_text=True)
    client.post("/admin/categories", data={"name": "Toys", "description": "Fun"})
    toys = Category.query.filter_by(name="Toys").one()
    client.post(f"/admin/categories/{toys.id}/delete")
    assert Category.query.filter_by(name="Toys").count() == 0

def test_customer_detail_shows_history_and_orders(client, demo, login_as):
    from marketplacex.modules.order import service as orders
    from marketplacex.modules.search.controller import SearchController
    SearchController.confirm_voice_text(demo.alice, "tai nghe")
    orders.checkout(demo.alice, {demo.book.id: 1}, "cod")
    login_as(client, "admin")
    html = client.get(f"/admin/customers/{demo.alice.id}").get_data(as_text=True)
    assert "tai nghe" in html and "voice" in html and "Sách Đắc Nhân Tâm" in html

def test_admin_cancel(client, demo, login_as):
    from marketplacex.modules.order import service as orders
    o = orders.checkout(demo.alice, {demo.book.id: 1}, "cod")[0]
    login_as(client, "admin")
    client.post(f"/admin/orders/{o.id}/cancel")
    assert o.status == "cancelled"

def test_admin_lists_render(client, demo, login_as):
    login_as(client, "admin")
    for url in ("/admin/categories", "/admin/customers", "/admin/orders"):
        assert client.get(url).status_code == 200
