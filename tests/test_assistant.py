from marketplacex.modules.assistant import service


def test_prompt_contains_products_policy_and_own_orders(demo):
    from marketplacex.modules.order import service as orders
    orders.checkout(demo.alice, {demo.book.id: 1}, "cod")
    p = service.build_system_prompt("iphone", demo.alice)
    assert "Apple iPhone 15" in p and "/products/" in p and "30,000" in p and "Sách Đắc Nhân Tâm x1" in p
    assert "voucher" not in p.lower() and "return" not in p.lower()
    assert "not logged in" in service.build_system_prompt("iphone", None)


def test_no_key_is_503(client, demo):
    r = client.post("/api/assistant", json={"message": "hi"})
    assert r.status_code == 503


def test_out_of_quota_key_hands_over_to_the_next(app, monkeypatch):
    import io, json, urllib.error
    app.config.update(GEMINI_API_KEY="k1", GEMINI_API_KEYS=["k2", "k3"])
    tried = []

    def fake(req, timeout):
        key = req.get_header("X-goog-api-key")
        tried.append(key)
        if key != "k3":
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps({"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}).encode())

    monkeypatch.setattr(service.urllib.request, "urlopen", fake)
    with app.app_context():
        assert service._call_gemini("sys", []) == "hi" and tried == ["k1", "k2", "k3"]
        tried.clear()
        assert service._call_gemini("sys", []) == "hi" and tried == ["k3"]   # remembers the working key
