"""Shopping assistant chatbot (Gemini). Gemini is never called in tests: _call_gemini is patched."""
import pytest

from helpers import paid_order, seller_user
from marketplacex.modules.assistant import service as assistant


@pytest.fixture
def fake_gemini(monkeypatch):
    calls = []

    def fake(system, contents):
        calls.append({"system": system, "contents": contents})
        return "Try the Logitech Wireless Mouse."
    monkeypatch.setattr(assistant, "_call_gemini", fake)
    return calls


def test_reply_grounded_in_catalogue(seeded, fake_gemini):
    assert assistant.ask("do you have a wireless mouse?", [], None) == "Try the Logitech Wireless Mouse."
    system = fake_gemini[0]["system"]
    assert "Logitech Wireless Mouse" in system and "/products/" in system and "429,000" in system
    assert "return window" in system.lower()


def test_history_passed_as_turns(seeded, fake_gemini):
    assistant.ask("and cheaper ones?", [{"role": "user", "text": "mouse?"}, {"role": "model", "text": "Logitech"}], None)
    roles = [c["role"] for c in fake_gemini[0]["contents"]]
    assert roles == ["user", "model", "user"]


def test_only_own_orders_in_context(alice, make_user, fake_gemini):
    o = paid_order(alice, "P03", 1)
    assistant.ask("where is my order?", [], alice)
    assert f"#{o.id}" in fake_gemini[0]["system"]
    assistant.ask("where is my order?", [], make_user("customer"))
    assert f"#{o.id}" not in fake_gemini[1]["system"]


def test_endpoint(client, seeded, fake_gemini):
    r = client.post("/api/assistant", json={"message": "hi", "history": []})
    assert r.status_code == 200 and r.json["reply"].startswith("Try")
    assert client.post("/api/assistant", json={"message": "  "}).status_code == 400


def test_gemini_failure_is_friendly(app, client, seeded, monkeypatch):
    import urllib.error
    app.config["GEMINI_API_KEY"] = "test-key"

    def boom(*a, **kw):
        raise urllib.error.URLError("network down")
    monkeypatch.setattr(assistant.urllib.request, "urlopen", boom)
    r = client.post("/api/assistant", json={"message": "hi"})
    assert r.status_code == 503 and "unavailable" in r.json["message"].lower()


def test_missing_key_is_friendly(app, seeded):
    app.config["GEMINI_API_KEY"] = ""
    with pytest.raises(assistant.AssistantUnavailable):
        assistant._call_gemini("sys", [{"role": "user", "parts": [{"text": "hi"}]}])


def test_rate_limit(client, seeded, fake_gemini):
    codes = [client.post("/api/assistant", json={"message": "hi"}).status_code for _ in range(22)]
    assert codes[:20] == [200] * 20 and codes[-1] == 429


def test_widget_only_for_customers(client, seeded, login):
    assert b'id="mx-assistant"' in client.get("/").data
    login(client, seller_user("sportzone@demo"))
    assert b'id="mx-assistant"' not in client.get("/seller/").data


def test_request_disables_thinking_so_replies_are_not_truncated(app, monkeypatch):
    import io
    import json as _json
    app.config["GEMINI_API_KEY"] = "test-key"
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        sent.update(_json.loads(req.data))
        return Resp(_json.dumps({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}).encode())
    monkeypatch.setattr(assistant.urllib.request, "urlopen", fake_urlopen)
    assert assistant._call_gemini("sys", [{"role": "user", "parts": [{"text": "hi"}]}]) == "ok"
    cfg = sent["generationConfig"]
    assert cfg["thinkingConfig"]["thinkingBudget"] == 0 and cfg["maxOutputTokens"] >= 1000
