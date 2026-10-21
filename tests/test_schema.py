from sqlalchemy import inspect
from marketplacex.extensions import db

TABLES = {
    "FullName": {"fullNameID", "firstName", "middleName", "lastName"},
    "Address": {"addressID", "ward", "street", "detail"},
    "Customer": {"customerID", "fullNameID", "addressID", "email", "phoneNumber"},
    "SearchHistory": {"searchHistoryID", "customerID", "keyword", "searchType", "searchedAt"},
    "Category": {"categoryID", "name", "description"},
    "Product": {"productID", "categoryID", "name", "brandName", "description", "price", "stockQuantity",
                "avgRating", "createdAt", "updatedAt"},
    "ProductImage": {"imageID", "productID", "imageUrl", "featureVector"},
    "Order": {"orderID", "customerID", "productID", "addressID", "quantity", "unitPrice", "shippingFee",
              "totalPrice", "paymentMethod", "paymentStatus", "status", "orderedAt", "shippedAt", "deliveredAt"},
}

def test_exactly_eight_tables_with_exact_columns(app):
    insp = inspect(db.engine)
    assert set(insp.get_table_names()) == set(TABLES)
    for name, cols in TABLES.items():
        assert {c["name"] for c in insp.get_columns(name)} == cols, name

def test_foreign_keys(app):
    insp = inspect(db.engine)
    fks = {(t, fk["constrained_columns"][0], fk["referred_table"]) for t in TABLES for fk in insp.get_foreign_keys(t)}
    assert fks == {("Customer", "fullNameID", "FullName"), ("Customer", "addressID", "Address"),
                   ("SearchHistory", "customerID", "Customer"), ("Product", "categoryID", "Category"),
                   ("ProductImage", "productID", "Product"), ("Order", "customerID", "Customer"),
                   ("Order", "productID", "Product"), ("Order", "addressID", "Address")}

def test_image_url_and_description_lengths():
    from marketplacex.modules.catalog.models import Product, ProductImage
    assert ProductImage.__table__.c.imageUrl.type.length == 500
    assert Product.__table__.c.description.type.length == 255

def test_demo_fixture_and_app_boots(client, demo):
    assert demo.alice.name == "Alice Nguyen"
    assert demo.alice.address.line == "12, Hoan Kiem, Hanoi, Trang Tien, Trang Tien"
    assert demo.iphone.image_vector is not None and demo.cheap.image_url is None
    assert client.get("/no-such-page").status_code == 404
