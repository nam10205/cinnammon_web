"""Live checks against the Supabase database (DATABASE_URL or the local config default).

Skipped by default (pytest.ini); run with `.venv/bin/python -m pytest -q -m supabase` after `init-db --reset`.
"""
import pytest
from sqlalchemy import create_engine, inspect, text

from tests.test_schema import TABLES

pytestmark = pytest.mark.supabase


@pytest.fixture(scope="module")
def engine():
    from marketplacex.config import Config
    if not str(Config.SQLALCHEMY_DATABASE_URI).startswith("postgresql"):
        pytest.skip("not a Postgres database")
    eng = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    yield eng
    eng.dispose()


def test_exactly_the_eight_tables_with_exact_columns(engine):
    insp = inspect(engine)
    assert set(insp.get_table_names(schema="public")) == set(TABLES)
    for table, cols in TABLES.items():
        assert {c["name"] for c in insp.get_columns(table, schema="public")} == cols, table


def test_rls_enabled_everywhere(engine):
    with engine.connect() as c:
        off = c.execute(text("SELECT relname FROM pg_class JOIN pg_namespace n ON n.oid = relnamespace "
                             "WHERE nspname = 'public' AND relkind = 'r' AND NOT relrowsecurity")).all()
    assert off == []


def test_fifty_products_per_category(engine):
    with engine.connect() as c:
        rows = c.execute(text('SELECT "categoryID", count(*) FROM "Product" GROUP BY 1')).all()
    assert len(rows) == 8 and all(n >= 50 for _, n in rows)
