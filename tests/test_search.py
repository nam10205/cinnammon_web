import io

import pytest
from PIL import Image

from marketplacex.errors import ValidationError
from marketplacex.modules.search.controller import InvalidKeyword, SearchController
from marketplacex.modules.search.dao import ProductDAO, ProductImageDAO, SearchHistoryDAO
from marketplacex.modules.search.images import solid_image
from marketplacex.modules.search.models import SearchHistory
from marketplacex.modules.search.query import SearchQuery, SearchRegion

def _two_colour_png():
    """Left half red (the iPhone's colour), right half blue (the Galaxy's)."""
    img = Image.new("RGB", (200, 100), (220, 30, 30))
    img.paste((30, 30, 220), (100, 0, 200, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def test_product_dao_find_by_keyword_matches_and_vietnamese(demo):
    assert [p.title for p in ProductDAO.find_by_keyword("iphone")] == ["Apple iPhone 15"]
    assert [p.title for p in ProductDAO.find_by_keyword("dac nhan tam")] == ["Sách Đắc Nhân Tâm"]
    assert ProductDAO.find_by_keyword("   ") == []
    assert [p.title for p in ProductDAO.find_by_keyword("phone under 16 trieu")] == ["Samsung Galaxy S24"]
    assert ProductDAO.find_by_id(demo.book.id) is demo.book

def test_product_image_dao_find_similar_ranks_by_colour(demo):
    from marketplacex.modules.search.images import feature_vector
    red = feature_vector(solid_image((210, 40, 40)))
    assert ProductImageDAO.find_similar(red)[0].product_id == demo.iphone.id
    assert demo.iphone.id not in [i.product_id for i in ProductImageDAO.find_similar(red, demo.iphone.id)]

@pytest.mark.parametrize("bad", ["", "   ", "iphone 📱", "❤️", "!!! ???", "a" * 101])
def test_validate_keyword_refuses_bad_keywords(bad):
    with pytest.raises(InvalidKeyword):
        SearchController.validate_keyword(bad)

def test_validate_keyword_accepts_vietnamese_and_prices():
    assert SearchController.validate_keyword("  Sách Đắc Nhân Tâm dưới 500k ") == "Sách Đắc Nhân Tâm dưới 500k"
    assert SearchController.validate_keyword("a" * 100) == "a" * 100

def test_invalid_keyword_shows_popup_and_is_not_saved(client, demo, login_as):
    login_as(client, "customer", demo.alice)
    for q in ("iphone 📱", "   ", "%%%"):
        r = client.get("/search", query_string={"q": q})
        html = r.get_data(as_text=True)
        assert r.status_code == 400 and 'id="popup-error"' in html and 'data-title="Invalid Keyword"' in html
        assert "Apple iPhone 15" not in html
    assert SearchHistory.query.count() == 0
    assert client.get("/search", query_string={"q": "điện thoại"}).status_code == 200
    assert client.get("/search").status_code == 200  # the camera button's page has no q at all

def test_text_and_voice_are_recorded_for_customers_only(client, demo, login_as):
    client.get("/search?q=iphone")
    assert SearchHistory.query.count() == 0
    login_as(client, "customer", demo.alice)
    client.get("/search?q=iphone")
    client.get("/search?q=samsung&mode=voice")
    client.get("/search?q=x&mode=weird")
    rows = [(h.keyword, h.search_type) for h in SearchHistory.query.order_by(SearchHistory.id)]
    assert rows == [("iphone", "text"), ("samsung", "voice"), ("x", "text")]

def test_image_upload_records_filename_and_rejects_non_images(client, demo, login_as):
    login_as(client, "customer", demo.alice)
    r = client.post("/search/image", data={"photo": (io.BytesIO(solid_image((220, 30, 30))), "red.png")},
                    content_type="multipart/form-data")
    assert "Apple iPhone 15" in r.get_data(as_text=True)
    assert SearchHistory.query.filter_by(search_type="image").one().keyword == "red.png"
    r = client.post("/search/image", data={"photo": (io.BytesIO(b"not an image"), "x.txt")},
                    content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and 'data-title="File error"' in html and "not an image" in html
    assert SearchHistory.query.filter_by(search_type="image").count() == 1

def test_similar(client, demo):
    html = client.get(f"/search?similar={demo.iphone.id}").get_data(as_text=True)
    assert "Similar to Apple iPhone 15" in html
    assert client.get("/search?similar=9999").status_code == 404
    assert SearchHistory.query.count() == 0

def test_navbar_has_mic_and_mode(client, demo):
    html = client.get("/").get_data(as_text=True)
    assert 'id="mic"' in html and 'name="mode"' in html and "js/voice_search_view.js" in html and 'id="camera"' in html


def test_photo_search_runs_gemini_label_as_text_search(client, demo, login_as, monkeypatch):
    from marketplacex.modules.search import images
    seen = {}
    monkeypatch.setattr(images, "describe", lambda data, cats: seen.setdefault("cats", cats) and "điện thoại iPhone")
    login_as(client, "customer", demo.alice)
    r = client.post("/search/image", data={"photo": (io.BytesIO(solid_image((220, 30, 30))), "phone.jpg")},
                    content_type="multipart/form-data")
    page = r.get_data(as_text=True)
    assert "Apple iPhone 15" in page and "Results for your photo" in page and 'value="điện thoại iPhone"' in page
    assert seen["cats"] and SearchHistory.query.filter_by(search_type="image").one().keyword == "phone.jpg"


def test_photo_search_falls_back_to_colour_when_gemini_times_out(client, demo, monkeypatch, app):
    import socket
    from marketplacex.modules.assistant import service as assistant
    app.config["GEMINI_API_KEY"] = "test-key"
    def slow(*a, **k):
        raise socket.timeout("The read operation timed out")
    monkeypatch.setattr(assistant.urllib.request, "urlopen", slow)
    r = client.post("/search/image", data={"photo": (io.BytesIO(solid_image((220, 30, 30))), "red.png")},
                    content_type="multipart/form-data")
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and "Results for your photo" in page and "matched by colour" in page


def test_history_api_lists_distinct_keywords_newest_first(client, demo, login_as, clock):
    assert client.get("/api/search/history").get_json() == {"items": []}
    login_as(client, "customer", demo.alice)
    for q, mode in (("iphone", "text"), ("sách", "voice"), ("IPHONE", "text")):
        client.get("/search", query_string={"q": q, "mode": mode})
        clock.advance(1)
    client.post("/search/image", data={"photo": (io.BytesIO(solid_image((220, 30, 30))), "red.png")},
                content_type="multipart/form-data")
    assert client.get("/api/search/history").get_json()["items"] == [
        {"q": "IPHONE", "type": "text"}, {"q": "sách", "type": "voice"}]


def test_validate_image_api_answers_ok_or_file_error(client):
    r = client.post("/api/search/image/validate", data={"photo": (io.BytesIO(_two_colour_png()), "p.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json() == {"ok": True, "width": 200, "height": 100}
    r = client.post("/api/search/image/validate", data={"photo": (io.BytesIO(b"nope"), "p.txt")},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["title"] == "File error" and "not an image" in r.get_json()["error"]
    with pytest.raises(ValidationError):
        SearchController.validate_image(b"")


def test_search_region_crops_to_the_marked_product(demo):
    photo = _two_colour_png()
    whole = SearchController.search_by_image(None, photo, None, "two.png", [])
    blue = SearchController.search_by_image(None, photo, SearchRegion(110, 5, 80, 90), "two.png", [])
    red = SearchController.search_by_image(None, photo, SearchRegion(0, 0, 100, 100), "two.png", [])
    assert [p.id for p in blue.products][:1] == [demo.galaxy.id] and demo.iphone.id not in [p.id for p in blue.products]
    assert [p.id for p in red.products][:1] == [demo.iphone.id]
    assert whole.note and "matched by colour" in whole.note


def test_search_region_parsing_and_clamping():
    assert SearchRegion.from_form({"x": "1.6", "y": "2", "width": "30", "height": "40"}) == SearchRegion(1, 2, 30, 40)
    assert SearchRegion.from_form({"x": "1"}) is None
    assert SearchRegion.from_form({"x": "0", "y": "0", "width": "0", "height": "5"}) is None
    img = Image.new("RGB", (100, 50))
    assert SearchRegion(90, 40, 50, 50).crop(img).size == (10, 10)
    assert SearchRegion(500, 500, 10, 10).crop(img).size == (100, 50)


def test_search_query_new_builds_history_rows(demo):
    q = SearchQuery.new("voice", "tai nghe")
    row = q.to_history(demo.alice)
    assert (row.keyword, row.search_type) == ("tai nghe", "voice")
    img = SearchQuery.new("image", "two.png", image=_two_colour_png(), region=SearchRegion(0, 0, 100, 100))
    assert img.type == "image" and img.vector and Image.open(io.BytesIO(img.image)).size == (100, 100)


def test_voice_text_is_saved_as_voice(client, demo, login_as):
    login_as(client, "customer", demo.alice)
    html = client.get("/search", query_string={"q": "samsung", "mode": "voice"}).get_data(as_text=True)
    assert "Samsung Galaxy S24" in html
    assert [(h.keyword, h.search_type) for h in SearchHistoryDAO.find_recent(demo.alice.id)] == [("samsung", "voice")]
