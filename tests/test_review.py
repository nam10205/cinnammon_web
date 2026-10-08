import pytest
from sqlalchemy.exc import IntegrityError

from helpers import delivered_order, offer_id, paid_order, product_id, seller_user
from marketplacex.errors import NotEligible, NotFound, ValidationError
from marketplacex.modules.catalog import service as catalog
from marketplacex.modules.review import service as review


def test_review_requires_delivery(alice):
    o = paid_order(alice, "P03", 1)
    with pytest.raises(NotEligible):
        review.create_review(alice, o.items[0].id, 5, "great")


def test_one_review_per_item_and_rating_updates(alice):
    o = delivered_order(alice, "P03")
    review.create_review(alice, o.items[0].id, 3, "ok")
    with pytest.raises((NotEligible, IntegrityError)):
        review.create_review(alice, o.items[0].id, 5, "again")
    off = catalog.get_offer(offer_id("P03"))
    assert off.rating_count == 1 and off.rating_avg == 3.0


def test_rating_bounds(alice):
    o = delivered_order(alice, "P03")
    with pytest.raises(ValidationError):
        review.create_review(alice, o.items[0].id, 6, "too good")


def test_other_customer_cannot_review(alice, make_user):
    o = delivered_order(alice, "P03")
    with pytest.raises(NotFound):
        review.create_review(make_user("customer"), o.items[0].id, 5, "x")


def test_seller_reply_and_product_page(client, alice):
    o = delivered_order(alice, "P03")
    r = review.create_review(alice, o.items[0].id, 4, "nice shoes")
    review.reply(seller_user("sportzone@demo"), r.id, "thanks")
    assert r.seller_reply == "thanks"
    with pytest.raises(NotFound):
        review.reply(seller_user("techhub@demo"), r.id, "hijack")
    html = client.get(f"/products/{product_id('P03')}").get_data(as_text=True)
    assert "nice shoes" in html and "thanks" in html


def test_hidden_review_not_shown(alice, make_user):
    o = delivered_order(alice, "P03")
    r = review.create_review(alice, o.items[0].id, 1, "spam spam")
    review.set_hidden(make_user("admin"), r.id, True, "spam")
    assert review.reviews_for_product(product_id("P03")) == []


def test_review_form_route(client, alice, login):
    o = delivered_order(alice, "P03")
    login(client, alice)
    url = f"/orders/{o.id}/items/{o.items[0].id}/review"
    assert client.get(url).status_code == 200
    client.post(url, data={"rating": "5", "comment": "perfect"})
    assert review.reviews_for_product(product_id("P03"))[0].comment == "perfect"
