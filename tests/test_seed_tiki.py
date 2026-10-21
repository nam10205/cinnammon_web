import copy

from marketplacex import tiki


def _small_snapshot():
    snap = copy.deepcopy(tiki.load_snapshot())
    for c in snap["categories"]:
        c["products"] = c["products"][:3]
    return snap


def test_seed_tiki_small(app):
    from marketplacex import seed_tiki
    from marketplacex.modules.catalog.models import Product
    counts = seed_tiki.run(_small_snapshot())
    assert counts["categories"] == 8 and counts["products"] == 24 and counts["customers"] == 10
    p = Product.query.first()
    assert p.images and p.price > 0 and p.stock_quantity >= 20


def test_seed_tiki_accounts_orders_and_reviews(app):
    from marketplacex import seed_tiki
    from marketplacex.modules.catalog.models import Category, Product
    from marketplacex.modules.chat.models import Conversation
    from marketplacex.modules.identity.models import Account
    from marketplacex.modules.order.models import Order
    from marketplacex.modules.promotion.models import Voucher
    from marketplacex.modules.review.models import Review
    from marketplacex.modules.seller.models import Shop
    counts = seed_tiki.run(_small_snapshot())
    assert counts["orders"] == 20 and counts["reviews"] == 20
    assert Order.query.filter_by(status="Delivered").count() == 20
    assert {r.rating for r in Review.query.all()} <= {4, 5}
    emails = {a.email: a.role for a in Account.query.all()}
    assert emails["admin@demo"] == "admin" and emails["alice@demo"] == "customer"
    for slug in ("techzone", "homenest", "stylehub", "glowupbeauty", "readmorebooks", "fitlife"):
        assert emails[f"{slug}@demo"] == "seller"
    assert all(s.verification_status == "verified" for s in Shop.query.all())
    assert Category.query.filter_by(name="Books").one().description == "Books from Tiki.vn"
    assert all(p.status == "active" and p.brand for p in Product.query.all())
    alice = Account.query.filter_by(email="alice@demo").one()
    assert alice.addresses and Conversation.query.filter_by(customer_id=alice.id).count() == 1
    assert Voucher.query.filter_by(code="SALE10").one()
    vectors = [i.feature_vector for p in Product.query.all() for i in p.images if i.feature_vector]
    assert vectors and all(len(v) > 0 for v in vectors)


def test_init_db_refuses_when_populated(app):
    from marketplacex.modules.identity import service
    service.create_account("x@x.vn", "X", "admin", "secret1")
    r = app.test_cli_runner().invoke(args=["init-db"])
    assert r.exit_code == 1 and "already initialised" in r.output


def test_enable_rls_noop_on_sqlite(app):
    from marketplacex.app import enable_rls
    assert enable_rls() == 0


def test_tiki_variants_split_counts_and_original_price():
    from marketplacex import seed_tiki
    p = {"tiki_id": 7, "price": 100000, "list_price": 120000, "rating": 4.5, "review_count": 7, "sold": 10,
         "options": ["Red", "Blue", "Red"]}
    vs = seed_tiki._variants(p)
    assert [v["name"] for v in vs] == ["Red", "Blue"]
    assert all(v["original_price_vnd"] == 120000 and 20 <= v["stock"] <= 200 for v in vs)
    assert sum(v["sold_count"] for v in vs) == 10 and sum(v["rating_count"] for v in vs) == 7
    same = seed_tiki._variants({**p, "list_price": 100000, "options": []})
    assert [v["name"] for v in same] == ["Default"] and same[0]["original_price_vnd"] is None
    assert seed_tiki.shop_email("GlowUp Beauty") == "glowupbeauty@demo"


def test_init_db_reset_seeds_small_snapshot(app, monkeypatch):
    small = _small_snapshot()
    monkeypatch.setattr(tiki, "load_snapshot", lambda: small)
    r = app.test_cli_runner().invoke(args=["init-db", "--reset"])
    assert r.exit_code == 0, r.output
    for line in ("categories: 8", "products: 24", "customers: 10", "orders: 20", "reviews: 20"):
        assert line in r.output
    assert "row level security" not in r.output


def test_engine_options_only_for_postgres():
    from marketplacex.app import create_app
    lite = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert "pool_size" not in lite.config.get("SQLALCHEMY_ENGINE_OPTIONS", {})
    pg = create_app({"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg2://u:p@localhost:1/db"})
    assert pg.config["SQLALCHEMY_ENGINE_OPTIONS"] == {"pool_pre_ping": True, "pool_size": 5}
