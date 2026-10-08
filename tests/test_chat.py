import pytest

from helpers import seller_user, shop_id
from marketplacex.errors import NotFound, ValidationError
from marketplacex.modules.chat import service as chat


def test_customer_seller_chat(alice):
    c = chat.get_or_create(alice, shop_id("SportZone"))
    assert chat.get_or_create(alice, shop_id("SportZone")).id == c.id
    chat.send(alice, c.id, "Is size 42 available?")
    chat.send(seller_user("sportzone@demo"), c.id, "Yes")
    assert [m.body for m in chat.messages(alice, c.id)] == ["Is size 42 available?", "Yes"]
    assert c in chat.conversations_for(seller_user("sportzone@demo"))


def test_outsider_cannot_read(alice):
    c = chat.get_or_create(alice, shop_id("SportZone"))
    with pytest.raises(NotFound):
        chat.messages(seller_user("techhub@demo"), c.id)


def test_empty_message_rejected(alice):
    c = chat.get_or_create(alice, shop_id("SportZone"))
    with pytest.raises(ValidationError):
        chat.send(alice, c.id, "   ")


def test_chat_routes(client, alice, login):
    login(client, alice)
    r = client.post("/chat/start", data={"shop_id": shop_id("TechHub")})
    url = r.headers["Location"]
    client.post(url + "/send", data={"body": "hello shop"})
    assert b"hello shop" in client.get(url).data
    login(client, seller_user("techhub@demo"))
    assert b"hello shop" in client.get(url).data
