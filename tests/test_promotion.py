import pytest

from helpers import alice_user, shop_id
from marketplacex.errors import VoucherExhausted, VoucherInvalid
from marketplacex.modules.promotion import service as promo
from marketplacex.modules.promotion.models import Redemption, Voucher


def test_report_example_discount(seeded):          # report §13.1: 2 Biti's + 2 vouchers -> discount 180,000
    sz = shop_id("SportZone")
    ev = promo.evaluate(alice_user(), {sz: 1798000}, {sz: 28000}, ["SALE10", "SPORT80"])
    assert sum(ev.item_discounts.values()) == 180000


def test_platform_discount_split_across_shops(seeded):
    sz, th = shop_id("SportZone"), shop_id("TechHub")
    ev = promo.evaluate(alice_user(), {sz: 300000, th: 100000}, {sz: 28000, th: 28000}, ["SALE10"])
    assert ev.item_discounts == {sz: 30000, th: 10000}
    assert ev.platform_discounts == {sz: 30000, th: 10000}


def test_min_spend_and_unknown_code(seeded):
    sz = shop_id("SportZone")
    with pytest.raises(VoucherInvalid):
        promo.evaluate(alice_user(), {sz: 100000}, {sz: 28000}, ["SPORT80"])
    with pytest.raises(VoucherInvalid):
        promo.evaluate(alice_user(), {sz: 100000}, {sz: 28000}, ["NOPE"])


def test_shop_voucher_needs_that_shop(seeded):
    with pytest.raises(VoucherInvalid):
        promo.evaluate(alice_user(), {shop_id("TechHub"): 900000}, {}, ["SPORT80"])


def test_redemption_unique_per_attempt(seeded):    # BR04
    sz = shop_id("SportZone")
    ev = promo.evaluate(alice_user(), {sz: 1798000}, {sz: 0}, ["SALE10"])
    a = promo.reserve(alice_user(), ev.applied, "att1", 15)
    b = promo.reserve(alice_user(), ev.applied, "att1", 15)
    assert [r.id for r in a] == [r.id for r in b]


def test_commit_and_release(seeded):
    sz = shop_id("SportZone")
    ev = promo.evaluate(alice_user(), {sz: 1798000}, {sz: 0}, ["SALE10"])
    promo.reserve(alice_user(), ev.applied, "a", 15)
    promo.commit("a", 1)
    v = Voucher.query.filter_by(code="SALE10").one()
    assert v.used_count == 1 and v.campaign.spent_vnd == 100000
    promo.reserve(alice_user(), ev.applied, "b", 15)
    promo.release("b")
    assert Redemption.query.filter_by(attempt_id="b").one().status == "released"


def test_exhausted(seeded):
    v = Voucher.query.filter_by(code="SPORT80").one()
    v.usage_limit = 0
    with pytest.raises(VoucherExhausted):
        promo.evaluate(alice_user(), {shop_id("SportZone"): 1798000}, {}, ["SPORT80"])


def test_campaign_page(client, seeded):
    from marketplacex.modules.promotion.models import Campaign
    c = Campaign.query.one()
    html = client.get(f"/campaigns/{c.id}").get_data(as_text=True)
    assert "10.10 Sale" in html and "SPORT80" in html and "Biti" in html
