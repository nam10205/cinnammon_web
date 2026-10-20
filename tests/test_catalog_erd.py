from marketplacex.extensions import db


def test_product_columns_match_erd(app):
    cols = {c.name for c in db.metadata.tables["Product"].columns}
    assert cols >= {"productID", "categoryID", "name", "brandName", "description", "price",
                    "stockQuantity", "avgRating", "createdAt", "updatedAt"}
    img = {c.name: c for c in db.metadata.tables["ProductImage"].columns}
    assert set(img) >= {"imageID", "productID", "imageUrl", "featureVector"}
    assert img["imageUrl"].type.length == 500


def test_price_and_stock_follow_offers(seeded):
    from helpers import _product, offer_id
    from marketplacex.modules.inventory import service as inventory
    p = _product("P03")
    assert p.price == min(v.offer.price_vnd for v in p.variants)
    inventory.set_stock(offer_id("P03"), 7)
    db.session.commit()
    assert p.stock_quantity == 7


def test_sync_product_with_no_offers(app, make_user):
    from marketplacex.modules.catalog import service as catalog
    from marketplacex.modules.catalog.models import Category, Product
    from marketplacex.modules.seller import service as seller
    shop = seller.create_shop(make_user("seller"), "S", "Hanoi", "")
    cat = Category(name="X"); db.session.add(cat); db.session.flush()
    p = Product(shop_id=shop.id, category_id=cat.id, title="Empty", status="draft")
    db.session.add(p); db.session.flush()
    catalog.sync_product(p)
    assert (p.price, p.stock_quantity, p.avg_rating) == (0, 0, 0)


def test_review_updates_avg_rating(alice):
    from helpers import delivered_order, _product
    from marketplacex.modules.review import service as review
    o = delivered_order(alice, "P07")
    review.create_review(alice, o.items[0].id, 2, "meh")
    assert _product("P07").avg_rating == 2.0


def test_image_url_property_uses_first_image(seeded):
    from helpers import _product
    p = _product("P01")
    assert p.image_url == p.images[0].url


def test_create_product_truncates_long_description(seeded):
    from helpers import cat
    from marketplacex.modules.catalog import service as catalog
    from marketplacex.modules.seller.models import Shop
    p = catalog.create_product(Shop.query.filter_by(name="SportZone").one(), cat("Shoes"), "Long Desc", "B",
                               "x" * 400, {}, [{"name": "Default", "price_vnd": 1000, "stock": 1}],
                               image_urls=["/a.png", "/b.png"])
    assert len(p.description) == 255 and p.description.endswith("...")
    assert [i.url for i in p.images] == ["/a.png", "/b.png"]
    assert p.image_vector is None


def test_validate_listing_rejects_long_description(seeded):
    from helpers import cat, valid_listing_data
    from marketplacex.modules.catalog import service as catalog
    d = valid_listing_data()
    errors = catalog.validate_listing(cat("Shoes"), d["title"], "y" * 256, d["attributes"], d["variants"])
    assert "Description must be 255 characters or fewer" in errors


def test_hiding_only_review_restores_avg_rating(alice):
    from helpers import delivered_order, _product, offer_id
    from marketplacex.modules.catalog import service as catalog
    from marketplacex.modules.review import service as review
    from marketplacex.modules.identity.models import Account
    admin = Account.query.filter_by(email="admin@demo").one()
    before = _product("P07").avg_rating
    o = delivered_order(alice, "P07")
    r = review.create_review(alice, o.items[0].id, 1, "bad")
    assert _product("P07").avg_rating == 1.0
    review.set_hidden(admin, r.id, True, "abusive")
    off = catalog.get_offer(offer_id("P07"))
    assert _product("P07").avg_rating == before and (off.rating_avg, off.rating_count) == (before, 0)
    review.set_hidden(admin, r.id, False, "restored")
    assert _product("P07").avg_rating == 1.0 and (off.rating_avg, off.rating_count) == (1.0, 1)


def _draft(**over):
    from helpers import valid_listing_data, seller_user, shop_id
    from marketplacex.modules.catalog import service as catalog
    data = {**valid_listing_data(), **over}
    return catalog.save_listing(seller_user("sportzone@demo"), shop_id("SportZone"), data, submit=False)


def test_draft_save_rejects_long_title(seeded):
    import pytest
    from marketplacex.errors import ValidationError
    with pytest.raises(ValidationError, match="Title must be 255 characters or fewer"):
        _draft(title="t" * 256)


def test_draft_and_submit_reject_long_brand(seeded):
    import pytest
    from helpers import cat, valid_listing_data
    from marketplacex.errors import ValidationError
    from marketplacex.modules.catalog import service as catalog
    with pytest.raises(ValidationError, match="Brand must be 255 characters or fewer"):
        _draft(brand="b" * 256)
    d = valid_listing_data()
    errors = catalog.validate_listing(cat("Shoes"), d["title"], d["description"], d["attributes"], d["variants"],
                                      brand="b" * 256)
    assert "Brand must be 255 characters or fewer" in errors
