import base64
from marketplacex import seed_tiki
from marketplacex.modules.search.images import solid_image, feature_vector, pack

def _snapshot(n=55):
    vec = base64.b64encode(pack(feature_vector(solid_image((10, 20, 30))))).decode()
    def prod(c, i):
        return {"tiki_id": f"{c}{i}", "name": f" Product {c}-{i} ", "brand": "" if i % 2 else "Brand",
                "description": "<p>Nice &amp; good</p>", "price": "123000", "rating": "4.5",
                "images": [f"https://salt.tikicdn.com/{c}/{i}/{k}.jpg" for k in range(4)], "vectors": [vec, None, vec, vec]}
    return {"categories": [{"name": f"Cat{c}", "shop": "x", "products": [prod(c, i) for i in range(n)]} for c in range(8)]}

def test_seed_counts_and_mapping(app):
    from marketplacex.modules.catalog.models import Product, ProductImage
    from marketplacex.modules.identity.models import Customer
    from marketplacex.modules.order.models import Order
    counts = seed_tiki.run(_snapshot())
    assert counts == {"FullName": 10, "Address": 10, "Customer": 10, "SearchHistory": 30, "Category": 8,
                      "Product": 440, "ProductImage": 1320, "Order": 20}
    p = Product.query.order_by(Product.id).first()
    assert p.title == "Product 0-0" and p.description == "Nice & good" and p.price == 123000 and 20 <= p.stock_quantity <= 200
    assert Product.query.filter_by(brand="Unbranded").count() == 216   # odd i of 0..54, 27 per category
    assert ProductImage.query.filter(ProductImage.feature_vector.is_(None)).count() == 440
    alice = Customer.query.filter_by(email="alice@demo").one()
    assert alice.name == "Alice Nguyen" and alice.address.detail == "12, Hoan Kiem, Hanoi" and alice.address.street == "Trang Tien"
    assert Order.query.filter_by(status="cancelled").count() == 2
    assert Order.query.filter_by(status="delivered").count() == 18

def test_init_db_refuses_without_reset(app):
    seed_tiki.run(_snapshot(1))
    result = app.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code == 1 and "use --reset" in result.output
