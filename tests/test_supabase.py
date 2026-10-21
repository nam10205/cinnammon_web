"""Live checks against the Supabase database (DATABASE_URL or the local config default).

Skipped by default (pytest.ini); run with `.venv/bin/python -m pytest -q -m supabase` after `init-db --reset`.
"""
import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.supabase
ERD = {
    "Address": {"addressID", "ward", "street", "detail"},
    "FullName": {"fullNameID", "firstName", "middleName", "lastName"},
    "Customer": {"customerID", "fullNameID", "addressID", "email", "phoneNumber"},
    "SearchHistory": {"searchHistoryID", "customerID", "keyword", "searchType", "searchedAt"},
    "Category": {"categoryID", "name", "description"},
    "Product": {"productID", "categoryID", "name", "brandName", "description", "price", "stockQuantity",
                "avgRating", "createdAt", "updatedAt"},
    "ProductImage": {"imageID", "productID", "imageUrl", "featureVector"},
}


@pytest.fixture(scope="module")
def engine():
    from marketplacex.config import Config
    eng = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    yield eng
    eng.dispose()


def test_erd_tables_and_columns(engine):
    insp = inspect(engine)
    for table, cols in ERD.items():
        assert cols <= {c["name"] for c in insp.get_columns(table)}, table


def test_fifty_products_per_category(engine):
    with engine.connect() as c:
        rows = c.execute(text('SELECT "categoryID", count(*) FROM "Product" GROUP BY 1')).all()
    assert len(rows) == 8 and all(n >= 50 for _, n in rows)


def test_rls_enabled_everywhere(engine):
    with engine.connect() as c:
        off = c.execute(text("SELECT relname FROM pg_class JOIN pg_namespace n ON n.oid = relnamespace "
                             "WHERE nspname = 'public' AND relkind = 'r' AND NOT relrowsecurity")).all()
    assert off == []
