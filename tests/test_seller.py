import pytest
from marketplacex.errors import ValidationError
from marketplacex.modules.catalog import service
from marketplacex.modules.search.images import solid_image

def test_save_product_rules(demo):
    p = service.save_product(None, demo.books.id, "New book", "  ", "short", 50_000, 10)
    assert p.brand == "Unbranded" and p.created_at is not None
    with pytest.raises(ValidationError, match="Description is too long"):
        service.save_product(p, demo.books.id, "New book", "", "x" * 256, 1, 1)
    with pytest.raises(ValidationError, match="Price must be 0 or more"):
        service.save_product(p, demo.books.id, "New book", "", "", -1, 1)

def test_add_image_computes_vector_or_none(demo):
    img = service.add_image(demo.cheap, "https://example.com/a.png", fetch=lambda u: solid_image((1, 2, 3)))
    assert img.feature_vector is not None
    def boom(u): raise OSError("down")
    assert service.add_image(demo.cheap, "https://example.com/b.png", fetch=boom).feature_vector is None
    with pytest.raises(ValidationError):
        service.add_image(demo.cheap, "ftp://x", fetch=boom)

def test_seller_pages_require_seller(client, demo, login_as):
    assert client.get("/seller/products").status_code == 302
    login_as(client, "customer", demo.alice)
    assert client.get("/seller/products").status_code == 403
    login_as(client, "seller")
    assert "Apple iPhone 15" in client.get("/seller/products").get_data(as_text=True)

def test_seller_edits_product_and_skips_order(client, demo, login_as):
    from marketplacex.modules.order import service as orders
    login_as(client, "seller")
    client.post(f"/seller/products/{demo.book.id}", data={"category_id": demo.books.id, "title": "Đắc Nhân Tâm (bìa cứng)",
                "brand": "", "description": "d", "price": 120_000, "stock": 7})
    assert (demo.book.title, demo.book.price, demo.book.stock_quantity) == ("Đắc Nhân Tâm (bìa cứng)", 120_000, 7)
    o = orders.checkout(demo.alice, {demo.book.id: 1}, "cod")[0]
    client.post(f"/seller/orders/{o.id}/skip")
    assert o.status == "processing"

def test_seller_pages_render(client, demo, login_as):
    login_as(client, "seller")
    assert client.get("/seller/products/new").status_code == 200
    assert client.get(f"/seller/products/{demo.book.id}").status_code == 200
    assert client.get("/seller/orders").status_code == 200
    r = client.post("/seller/products/new", data={"category_id": demo.books.id, "title": "Z", "price": 1, "stock": 1})
    assert r.status_code == 302
