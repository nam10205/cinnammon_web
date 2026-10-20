from marketplacex.extensions import db


def test_register_creates_customer_and_fullname(app):
    from marketplacex.modules.identity import service
    a = service.register("lan@x.vn", "secret1", "Lan Thi Tran")
    c = a.customer
    assert (c.full_name.first_name, c.full_name.middle_name, c.full_name.last_name) == ("Lan", "Thi", "Tran")
    assert c.email == "lan@x.vn" and c.account_id == a.id


def test_seller_has_no_customer_row(app, make_user):
    assert make_user("seller").customer is None


def test_default_address_sets_customer_addressID(app, make_user):
    from marketplacex.modules.identity import service
    u = make_user()
    a1 = service.add_address(u, "Lan", "0901", "12 Trang Tien", "Trang Tien", "Hoan Kiem", "Hanoi")
    a2 = service.add_address(u, "Lan", "0901", "5 Le Loi", "Ben Nghe", "District 1", "Ho Chi Minh City", is_default=True)
    assert u.customer.address_id == a2.id and not a1.is_default
    assert a2.as_dict()["line"] == "5 Le Loi, Ben Nghe, District 1"


def test_seller_cannot_add_address(app, make_user):
    import pytest
    from marketplacex.errors import ValidationError
    from marketplacex.modules.identity import service
    with pytest.raises(ValidationError):
        service.add_address(make_user("seller"), "S", "0", "st", "w", "d", "c")


def test_erd_table_and_column_names(app):
    t = db.metadata.tables
    assert {c.name for c in t["Customer"].columns} >= {"customerID", "fullNameID", "addressID", "email", "phoneNumber"}
    assert {c.name for c in t["FullName"].columns} == {"fullNameID", "firstName", "middleName", "lastName"}
    assert {c.name for c in t["Address"].columns} >= {"addressID", "ward", "street", "detail"}


def test_drop_create_twice(app):
    for _ in range(2):
        db.drop_all()
        db.create_all()


def test_account_address_form_posts_erd_fields(app, client, make_user, login):
    u = make_user()
    login(client, u)
    r = client.post("/account/addresses", data={"recipient": "Lan", "phone": "0901", "detail": "Apt 3",
                                                "street": "12 Trang Tien", "ward": "Trang Tien",
                                                "district": "Hoan Kiem", "city": "Hanoi"})
    assert r.status_code == 302
    a = u.addresses[0]
    assert (a.street, a.ward, a.district, a.detail, a.is_default) == ("12 Trang Tien", "Trang Tien", "Hoan Kiem", "Apt 3", True)
    assert "Apt 3, 12 Trang Tien, Trang Tien, Hoan Kiem" in client.get("/account").get_data(as_text=True)
