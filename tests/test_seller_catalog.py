import pytest

from helpers import cat, offer_id, product_id, seller_user, shop_id, valid_listing_data
from marketplacex.errors import NotFound, StaleVersion, ValidationError
from marketplacex.modules.catalog import service as catalog
from marketplacex.modules.inventory import service as inventory
from marketplacex.modules.seller import service as seller_svc


def test_listing_validation_messages(seeded):
    errs = catalog.validate_listing(cat("Shoes"), "Counterfeit Nike", "", {"color": "black"},
                                    [{"name": "A", "price_vnd": 0, "stock": 1}, {"name": "A", "price_vnd": 5, "stock": 1}])
    assert any("size" in e for e in errs) and any("prohibited" in e.lower() for e in errs)
    assert any("duplicate" in e.lower() for e in errs) and any("price" in e.lower() for e in errs)


def test_submit_goes_pending(seeded):
    p = catalog.save_listing(seller_user("sportzone@demo"), shop_id("SportZone"), valid_listing_data(), submit=True)
    assert p.status == "pending" and len(p.variants) == 2
    assert inventory.in_stock(p.variants[1].offer.id) == 5


def test_draft_save_skips_validation(seeded):
    d = valid_listing_data()
    d["attributes"] = {}
    p = catalog.save_listing(seller_user("sportzone@demo"), shop_id("SportZone"), d, submit=False)
    assert p.status == "draft"


def test_unverified_shop_cannot_submit(seeded):
    s = seller_user("sportzone@demo")
    sh = seller_svc.create_shop(s, "New", "Hue")
    with pytest.raises(ValidationError):
        catalog.save_listing(s, sh.id, valid_listing_data(), submit=True)


def test_other_sellers_shop_rejected(seeded):
    with pytest.raises(NotFound):
        catalog.save_listing(seller_user("techhub@demo"), shop_id("SportZone"), valid_listing_data(), submit=True)


def test_editing_active_title_requires_moderation(seeded):
    s = seller_user("sportzone@demo")
    p = catalog.get_product(product_id("P03"))
    d = valid_listing_data()
    d["title"] = "Biti's Hunter Black Sneakers v2"
    d["variants"] = [{"name": "Default", "price_vnd": 899000, "stock": 50, "purchase_limit": 5}]
    catalog.save_listing(s, shop_id("SportZone"), d, product_id=p.id, submit=True)
    assert p.status == "pending"


def test_update_offer_and_stale(seeded):
    s = seller_user("sportzone@demo")
    o = catalog.get_offer(offer_id("P03"))
    seller_svc.update_offer(s, o.id, 850000, 1050000, 40, 4, o.version)
    assert (o.price_vnd, inventory.in_stock(o.id), o.purchase_limit) == (850000, 40, 4)
    with pytest.raises(StaleVersion):
        seller_svc.update_offer(s, o.id, 1, None, 1, 5, o.version - 1)
    with pytest.raises(NotFound):
        seller_svc.update_offer(seller_user("techhub@demo"), o.id, 1, None, 1, 5, o.version)


def test_shop_profile_and_verification(seeded):
    s = seller_user("sportzone@demo")
    sh = seller_svc.create_shop(s, "SportZone Outlet", "Hanoi")
    seller_svc.submit_verification(s, sh.id, "Business licence 0101")
    assert sh.verification_status == "pending"


def test_seller_catalog_pages(client, seeded, login):
    login(client, seller_user("sportzone@demo"))
    for p in ["/seller/products", "/seller/products/new", f"/seller/products/{product_id('P03')}/edit",
              "/seller/inventory", "/seller/shop"]:
        assert client.get(p).status_code == 200, p
    r = client.post("/seller/products/new", data={
        "category_id": cat("Shoes").id, "title": "Web Listing", "brand": "X", "description": "d",
        "attr_key": ["size", "color"], "attr_value": ["40", "red"],
        "variant_name": ["Default"], "variant_price": ["500000"], "variant_original": [""], "variant_stock": ["3"],
        "variant_limit": ["2"], "submit": "1"}, follow_redirects=True)
    assert r.status_code == 200
    from marketplacex.modules.catalog.models import Product
    assert Product.query.filter_by(title="Web Listing").one().status == "pending"
