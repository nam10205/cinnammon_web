from marketplacex.modules.catalog import service

def test_category_sorting_and_price_filter(demo):
    items, total = service.category_products(demo.phones.id, sort="price_asc")
    assert [p.title for p in items] == ["Samsung Galaxy S24", "Apple iPhone 15"] and total == 2
    items, total = service.category_products(demo.phones.id, max_price=16_000_000)
    assert [p.title for p in items] == ["Samsung Galaxy S24"] and total == 1
    items, _ = service.category_products(demo.phones.id, sort="bogus")
    assert items[0].title == "Apple iPhone 15"   # falls back to rating

def test_pages_render(client, demo):
    assert "Apple iPhone 15" in client.get("/").get_data(as_text=True)
    assert "Samsung Galaxy S24" in client.get(f"/categories/{demo.phones.id}").get_data(as_text=True)
    html = client.get(f"/products/{demo.iphone.id}").get_data(as_text=True)
    assert "20,000,000" in html and f"/search?similar={demo.iphone.id}" in html
    assert "Out of stock" in client.get(f"/products/{demo.cheap.id}").get_data(as_text=True)

def test_missing_product_and_category_are_404(client, demo):
    assert client.get("/products/9999").status_code == 404
    assert client.get("/categories/9999").status_code == 404
