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
