"""Extended demo catalogue from the dummyjson snapshot, with online product photos."""
import pytest

from helpers import product_id
from marketplacex.modules.catalog.models import Product
from marketplacex.modules.search import service as search_service
from marketplacex.modules.search.query import build_query
from marketplacex.modules.seller.models import Shop


@pytest.fixture
def bulk(seeded):
    from marketplacex import seed
    seed.seed_bulk_catalog()
    return True


def test_bulk_catalog_loaded(bulk):
    assert Product.query.filter_by(status="active").count() >= 190
    assert Shop.query.count() >= 8
    from marketplacex.modules.catalog.models import Category
    assert Category.query.filter_by(name="Smartphones").one().parent.name == "Electronics"


def test_every_active_product_has_online_photo(bulk):
    for p in Product.query.filter_by(status="active").all():
        assert p.image_url.startswith("https://"), p.title


def test_prices_converted_to_vnd(bulk):
    p = Product.query.filter_by(title="Essence Mascara Lash Princess").one()
    o = p.variants[0].offer
    assert o.price_vnd == 250000 and o.price_vnd % 1000 == 0      # 9.99 USD * 25,000 rounded
    assert o.original_price_vnd > o.price_vnd                     # 7.17% discount basis shown


@pytest.mark.parametrize("mode,text,image,top", [
    ("text", "black running shoes under 2 million", None, "P01"),
    ("voice", "wireless mouse under 500k", None, "P07"),
    pytest.param("image", "", "black-sneaker", "P03",
                 marks=pytest.mark.xfail(strict=True, reason="vectors in Task 6")),
    ("text", "giày chạy bộ màu đen", None, "P01"),
])
def test_prototype_results_survive_bulk_catalog(bulk, mode, text, image, top):
    r = search_service.search(build_query(mode, text=text, image_key=image))
    assert r.items[0].product.id == product_id(top)


def test_new_shop_logins_and_pages(client, bulk):
    client.post("/demo-login/customer")
    assert b"Smartphones" in client.get("/").data
    phone = Product.query.filter_by(title="iPhone 9").first() or Product.query.join(Product.category).filter_by(name="Smartphones").first()
    assert client.get(f"/products/{phone.id}").status_code == 200
    client.get("/logout")
    from marketplacex.modules.identity.models import Account
    assert Account.query.filter_by(email="homenest@demo", role="seller").one()


def test_extra_customers_with_reviews(bulk):
    from marketplacex import seed
    from marketplacex.modules.review.models import Review
    seed.seed_extra_customers()
    assert Review.query.count() >= 3
    for r in Review.query.all():
        assert r.order_item.order.status in ("Delivered", "Completed")   # BR06 holds for seeded reviews
