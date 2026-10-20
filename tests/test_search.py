import pytest

from helpers import product_id
from marketplacex.modules.search import service as search_service
from marketplacex.modules.search.query import build_query


@pytest.mark.parametrize("mode,text,image,top", [
    ("text", "black running shoes under 2 million", None, "P01"),
    ("voice", "wireless mouse under 500k", None, "P07"),
    pytest.param("image", "", "black-sneaker", "P03",
                 marks=pytest.mark.xfail(strict=True, reason="vectors in Task 6")),
    ("text", "giày chạy bộ màu đen", None, "P01"),
])
def test_prototype_top_results(seeded, mode, text, image, top):
    r = search_service.search(build_query(mode, text=text, image_key=image))
    assert r.items[0].product.id == product_id(top)


def test_query_object_common_across_modes(app):
    t = build_query("text", "black running shoes under 2 million")
    v = build_query("voice", "wireless mouse under 500k")
    assert (t.type, t.terms, t.max_price) == ("text", ["black", "running", "shoes"], 2000000)
    assert (v.type, v.terms, v.max_price) == ("voice", ["wireless", "mouse"], 500000)


def test_price_ceiling_applied_before_ranking(seeded):
    r = search_service.search(build_query("text", "running shoes under 2 million"))
    assert product_id("P02") not in [i.product.id for i in r.items]


def test_empty_results_give_relax_hints(seeded):
    r = search_service.search(build_query("text", "headphones under 100k"))
    assert r.items == [] and any("price" in h.lower() for h in r.relax_hints)


def test_unknown_image_falls_back_to_text_degraded(seeded):
    r = search_service.search(build_query("image", text="mouse", image_key="upload"))
    assert r.degraded and r.items[0].product.id == product_id("P07")


def test_no_keywords_lists_by_sales(seeded):            # Review Focus 4
    r = search_service.search(build_query("text", "under 500k"))
    assert r.items and all(i.offer.price_vnd <= 500000 for i in r.items)
    assert r.items[0].product.id == product_id("P11")    # 5000 sold
    assert search_service.search(build_query("text", "")).items


def test_sort_price_deterministic(seeded):
    r = search_service.search(build_query("text", "shoes", sort="price_asc"))
    prices = [i.offer.price_vnd for i in r.items]
    assert prices == sorted(prices) and len(prices) >= 4


def test_filters_and_facets(seeded):
    from helpers import cat
    r = search_service.search(build_query("text", "black", filters={"category_id": cat("Shoes").id}))
    assert {i.product.category.name for i in r.items} == {"Shoes"}
    assert dict(r.facets["brand"])  # facet counts present


def test_search_writes_trace(seeded):
    from marketplacex.modules.search.models import SearchTrace
    r = search_service.search(build_query("text", "zzzz"))
    t = SearchTrace.query.filter_by(trace_id=r.trace_id).one()
    assert t.result_count == 0


def test_recommend_popular_without_customer(seeded):
    recs = search_service.recommend(None)
    assert recs and recs[0][1] == "Popular now"


def test_search_page_renders(client, seeded):
    assert b"Nike Air Zoom" in client.get("/search?q=black+running+shoes").data
    assert b"degraded" in client.get("/search?mode=image&image=upload&q=mouse").data.lower()
