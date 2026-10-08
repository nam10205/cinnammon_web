import pytest
from sqlalchemy.exc import IntegrityError

from helpers import offer_id, product_id
from marketplacex.errors import InsufficientStock
from marketplacex.extensions import db
from marketplacex.modules.admin import policy
from marketplacex.modules.inventory import service as inventory


def test_offer_unique_per_shop_variant(seeded):          # BR01
    from marketplacex.modules.catalog.models import Offer
    o = Offer.query.first()
    db.session.add(Offer(shop_id=o.shop_id, variant_id=o.variant_id, price_vnd=1))
    with pytest.raises(IntegrityError):
        db.session.flush()


def test_reserve_commit_release_never_negative(seeded):
    oid = offer_id("P03")
    inventory.set_stock(oid, 2)
    inventory.reserve([(oid, 2)], "a1", 15)
    with pytest.raises(InsufficientStock):
        inventory.reserve([(oid, 1)], "a2", 15)
    inventory.reserve([(oid, 2)], "a1", 15)                 # idempotent
    led = inventory.get_ledger(oid)
    assert (led.available, led.reserved) == (0, 2)
    inventory.release("a1")
    led = inventory.get_ledger(oid)
    assert (led.available, led.reserved) == (2, 0)


def test_commit_moves_reserved_to_committed(seeded):
    oid = offer_id("P03")
    inventory.reserve([(oid, 3)], "c1", 15)
    inventory.commit("c1")
    inventory.commit("c1")
    led = inventory.get_ledger(oid)
    assert (led.available, led.reserved, led.committed) == (47, 0, 3)
    inventory.return_committed(oid, 1)
    assert inventory.get_ledger(oid).available == 48


def test_sweep_releases_expired(seeded):
    oid = offer_id("P03")
    inventory.reserve([(oid, 1)], "a3", 15)
    policy.advance_clock(1)
    assert inventory.sweep_expired() == ["a3"]
    assert inventory.get_ledger(oid).reserved == 0


def test_product_page_shows_commercial_fields(client, seeded):
    html = client.get(f"/products/{product_id('P01')}").get_data(as_text=True)
    for s in ["Nike Air Zoom", "1,990,000", "2,490,000", "SportZone", "4.9", "1,200"]:
        assert s in html, s


def test_home_category_and_shop_pages(client, seeded):
    from helpers import cat, shop_id
    assert b"Fashion" in client.get("/").data
    assert b"Biti" in client.get(f"/category/{cat('Shoes').id}").data
    assert b"Logitech" in client.get(f"/shops/{shop_id('TechHub')}").data
