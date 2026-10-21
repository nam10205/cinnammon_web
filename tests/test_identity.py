def test_quick_logins(client, demo):
    r = client.post("/login/quick/customer")
    with client.session_transaction() as s:
        assert s["role"] == "customer" and s["customer_id"] == demo.alice.id
    client.post("/logout")
    client.post("/login/quick/seller")
    with client.session_transaction() as s:
        assert s["role"] == "seller" and "customer_id" not in s
    client.post("/login/quick/admin")
    with client.session_transaction() as s:
        assert s["role"] == "admin"

def test_login_page_shows_three_buttons_and_email_box(client, demo):
    html = client.get("/login").get_data(as_text=True)
    assert "/login/quick/customer" in html and "/login/quick/seller" in html and "/login/quick/admin" in html
    assert 'name="email"' in html and 'type="password"' not in html

def test_email_login_is_case_insensitive_and_trimmed(client, demo):
    client.post("/login/email", data={"email": "  ALICE@Demo "})
    with client.session_transaction() as s:
        assert s["customer_id"] == demo.alice.id

def test_unknown_email_is_refused(client, demo):
    r = client.post("/login/email", data={"email": "nobody@demo"}, follow_redirects=True)
    assert "No customer with that email" in r.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "role" not in s

def test_signup_creates_rows_and_logs_in(client, demo):
    from marketplacex.modules.identity.models import Customer
    client.post("/signup", data={"first_name": "Mai", "middle_name": "", "last_name": "Pham", "email": " Mai@Test.vn ",
                                 "phone": "0901", "ward": "Ben Nghe", "street": "Le Loi", "detail": "5, Quận 1, TP.HCM"})
    c = Customer.query.filter_by(email="mai@test.vn").one()
    assert c.name == "Mai Pham" and c.address.detail == "5, Quận 1, TP.HCM"
    with client.session_transaction() as s:
        assert s["customer_id"] == c.id

def test_signup_rejects_duplicate_and_missing(demo):
    import pytest
    from marketplacex.errors import ValidationError
    from marketplacex.modules.identity import service
    with pytest.raises(ValidationError, match="already exists"):
        service.signup("A", "", "B", "ALICE@demo", "1", "w", "s", "d")
    with pytest.raises(ValidationError, match="Street is required"):
        service.signup("A", "", "B", "new@demo", "1", "w", " ", "d")

def test_profile_address_change_creates_new_row(demo):
    from marketplacex.modules.identity import service
    old = demo.alice.address_id
    service.update_profile(demo.alice, "Alice", "", "Nguyen", "0912345678", "Trang Tien", "Trang Tien", "12, Hoan Kiem, Hanoi")
    assert demo.alice.address_id == old
    service.update_profile(demo.alice, "Alice", "", "Nguyen", "0999", "Ben Nghe", "Le Loi", "45, Quận 1, TP.HCM")
    assert demo.alice.address_id != old and demo.alice.phone_number == "0999"

def test_profile_requires_customer(client, demo, login_as):
    assert client.get("/profile").status_code == 302
    login_as(client, "seller")
    assert client.get("/profile").status_code == 403
