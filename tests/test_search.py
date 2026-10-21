import pytest

from helpers import image_vec, product_id
from marketplacex.modules.search import service as search_service
from marketplacex.modules.search.query import build_query


@pytest.mark.parametrize("mode,text,image,top", [
    ("text", "black running shoes under 2 million", None, "P01"),
    ("voice", "wireless mouse under 500k", None, "P07"),
    ("image", "", "black", "P01"),   # identical black vectors tie on similarity; ranking score (rating) picks P01
    ("text", "giày chạy bộ màu đen", None, "P01"),
])
def test_prototype_top_results(seeded, mode, text, image, top):
    r = search_service.search(build_query(mode, text=text, image_vector=image_vec(image)))
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
    r = search_service.search(build_query("image", text="mouse", image_vector=None))
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
    assert b"degraded" in client.get("/search?mode=image&q=mouse").data.lower()


def test_search_history_rows(client, alice, login):
    from marketplacex.modules.search.models import SearchHistory
    login(client, alice)
    client.get("/search?q=sneakers")
    row = SearchHistory.query.one()
    assert (row.keyword, row.search_type, row.customer_id) == ("sneakers", "text", alice.customer.id)


def test_feature_vector_shape_and_similarity():
    from marketplacex.modules.search.images import feature_vector, solid_image
    from marketplacex.modules.search.ranking import cosine
    black, black2, white = (feature_vector(solid_image(c)) for c in [(20, 20, 20), (25, 25, 25), (240, 240, 240)])
    assert len(black) == 64
    assert cosine(black, black2) > 0.99 and cosine(black, white) < 0.1


def test_pack_unpack_roundtrip():
    from marketplacex.modules.search.images import feature_vector, pack, solid_image, unpack
    v = feature_vector(solid_image((20, 20, 20)))
    assert unpack(pack(v)) == pytest.approx(v) and unpack(None) is None


def test_upload_black_photo_finds_black_products(client, seeded):
    import io
    from marketplacex.modules.search.images import solid_image
    r = client.post("/search/image", data={"photo": (io.BytesIO(solid_image((20, 20, 20))), "q.png")},
                    content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Biti&#39;s Hunter Black Sneakers" in html and "Women Linen Summer Dress" not in html


def test_upload_non_image_flashes_error(client, seeded):
    import io
    r = client.post("/search/image", data={"photo": (io.BytesIO(b"not an image"), "x.jpg")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200 and "That file is not an image" in r.get_data(as_text=True)


def test_upload_missing_photo_flashes(client, seeded):
    r = client.post("/search/image", data={}, content_type="multipart/form-data", follow_redirects=True)
    assert "Choose a photo to search with" in r.get_data(as_text=True)


def test_image_search_records_history(client, alice, login):
    import io
    from marketplacex.modules.search.images import solid_image
    from marketplacex.modules.search.models import SearchHistory
    login(client, alice)
    client.post("/search/image", data={"photo": (io.BytesIO(solid_image((20, 20, 20))), "q.png")},
                content_type="multipart/form-data")
    row = SearchHistory.query.one()
    assert (row.keyword, row.search_type) == ("[image]", "image")


def test_find_similar_link_and_search(client, seeded):
    from helpers import product_id
    pid = product_id("P09")
    assert f"/search?similar={pid}".encode() in client.get(f"/products/{pid}").data
    html = client.get(f"/search?similar={pid}").get_data(as_text=True)
    assert "Women Linen Summer Dress" in html and "Biti&#39;s Hunter" not in html


def test_upload_results_hide_filter_form(client, seeded):
    import io
    from marketplacex.modules.search.images import solid_image
    html = client.post("/search/image", data={"photo": (io.BytesIO(solid_image((20, 20, 20))), "q.png")},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert 'name="sort"' not in html and "Filters aren" in html
    assert 'name="sort"' in client.get("/search?q=shoes").get_data(as_text=True)


def test_similar_unknown_product_is_404(client, seeded):
    assert client.get("/search?similar=999999").status_code == 404


def _count_queries(fn):
    from sqlalchemy import event
    from marketplacex.extensions import db
    n = [0]

    def _c(*a):
        n[0] += 1
    event.listen(db.engine, "before_cursor_execute", _c)
    try:
        fn()
    finally:
        event.remove(db.engine, "before_cursor_execute", _c)
    return n[0]


def test_search_and_listing_queries_do_not_grow_per_offer(seeded, client):
    """A remote database (Supabase, ~90 ms a round trip) cannot afford one lazy load per offer."""
    from marketplacex.extensions import db
    from marketplacex.modules.search import service
    from marketplacex.modules.search.query import build_query
    db.session.expunge_all()
    n = _count_queries(lambda: service.search(build_query("text", "")))
    assert n <= 12, n
    db.session.expunge_all()
    n = _count_queries(lambda: client.get("/search?q="))
    assert n <= 20, n
    from helpers import cat
    cid = cat("Fashion").id
    db.session.expunge_all()
    n = _count_queries(lambda: client.get(f"/category/{cid}"))
    assert n <= 15, n
    client.post("/demo-login/customer")
    client.get("/search?q=shoes")   # gives alice a recent search, so recommendations run a search too
    db.session.expunge_all()
    n = _count_queries(lambda: client.get("/"))
    assert n <= 60, n


@pytest.fixture
def vn_products(seeded):
    from helpers import cat
    from marketplacex.extensions import db
    from marketplacex.modules.catalog import service as catalog
    from marketplacex.modules.seller.models import Shop
    shop = Shop.query.filter_by(name="SportZone").one()
    ids = {}
    for key, title in (("shirt", "Áo thun nam cotton"), ("mouse", "Chuột không dây Logitech")):
        p = catalog.create_product(shop, cat("Shoes"), title, "B", "d", {}, [{"name": "Default", "price_vnd": 1000, "stock": 5}])
        p.status = "active"
        ids[key] = p.id
    db.session.commit()
    return ids


@pytest.mark.parametrize("text,key", [("áo thun", "shirt"), ("ao", "shirt"), ("chuột không dây", "mouse")])
def test_vietnamese_query_matches_vietnamese_title(vn_products, text, key):
    r = search_service.search(build_query("text", text=text))
    assert vn_products[key] in [i.product.id for i in r.items]
