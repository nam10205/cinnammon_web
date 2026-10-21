import io
from marketplacex.modules.search import service
from marketplacex.modules.search.images import solid_image
from marketplacex.modules.search.models import SearchHistory

def test_text_search_matches_and_vietnamese(demo):
    assert [p.title for p in service.search_text("iphone")] == ["Apple iPhone 15"]
    assert [p.title for p in service.search_text("dac nhan tam")] == ["Sách Đắc Nhân Tâm"]
    assert service.search_text("   ") == []
    assert [p.title for p in service.search_text("phone under 16 trieu")] == ["Samsung Galaxy S24"]

def test_vector_search_ranks_by_colour(demo):
    from marketplacex.modules.search.images import feature_vector
    red = feature_vector(solid_image((210, 40, 40)))
    assert service.search_vector(red)[0].id == demo.iphone.id
    assert demo.iphone.id not in [p.id for p in service.search_vector(demo.iphone.image_vector, exclude_id=demo.iphone.id)]

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
                    content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200 and "That file is not an image" in r.get_data(as_text=True)

def test_similar(client, demo):
    html = client.get(f"/search?similar={demo.iphone.id}").get_data(as_text=True)
    assert "Similar to Apple iPhone 15" in html
    assert client.get("/search?similar=9999").status_code == 404
    assert SearchHistory.query.count() == 0

def test_navbar_has_mic_and_mode(client, demo):
    html = client.get("/").get_data(as_text=True)
    assert 'id="mic"' in html and 'name="mode"' in html and "js/voice.js" in html
