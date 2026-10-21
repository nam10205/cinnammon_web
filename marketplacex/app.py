"""MarketplaceX application factory: a modular monolith (report §15)."""
from __future__ import annotations

import importlib
import os
import uuid

import click
from flask import Flask, flash, g, jsonify, redirect, render_template, request, session
from sqlalchemy import inspect, text

from .config import Config
from .errors import DomainError
from .extensions import db

MODULES = ["identity", "catalog", "search", "cart", "order", "seller", "admin", "assistant"]


def _import_optional(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name == name or (e.name and name.startswith(e.name)):
            return None
        raise


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    if str(app.config["SQLALCHEMY_DATABASE_URI"]).startswith("postgresql") \
            and not app.config.get("SQLALCHEMY_ENGINE_OPTIONS"):
        # A remote pooler (Supabase) drops idle connections; SQLite's pool rejects pool_size.
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_size": 5}
    os.makedirs(os.path.join(os.path.dirname(app.root_path), "instance"), exist_ok=True)
    db.init_app(app)

    for m in MODULES:
        for part in ("models", "service"):
            _import_optional(f"marketplacex.modules.{m}.{part}")
        routes = _import_optional(f"marketplacex.modules.{m}.routes")
        if routes is not None and hasattr(routes, "bp"):
            app.register_blueprint(routes.bp)

    _register_helpers(app)
    _register_errors(app)
    _register_cli(app)
    return app


def _register_helpers(app: Flask) -> None:
    from . import auth

    @app.before_request
    def _correlation():
        g.correlation_id = uuid.uuid4().hex
        g.pop("current_customer", None)  # tests share one app context across requests

    @app.template_filter("vnd")
    def vnd(v):
        return f"{int(v or 0):,} ₫"

    @app.template_filter("dt")
    def dt(v):
        return v.strftime("%Y-%m-%d %H:%M") if v else ""

    def has_endpoint(name: str) -> bool:
        return name in app.view_functions

    @app.context_processor
    def _ctx():
        cart = session.get("cart", {})
        cart_count = sum(int(q) for q in cart.values()) if isinstance(cart, dict) else 0
        return {"role": auth.current_role(), "customer": auth.current_customer(),
                "has_endpoint": has_endpoint, "cart_count": cart_count}


def _wants_json() -> bool:
    return (request.is_json or request.path.startswith("/api/")
            or request.path.startswith("/payments/callback"))


def _register_errors(app: Flask) -> None:
    @app.errorhandler(DomainError)
    def _domain(e: DomainError):
        db.session.rollback()
        if _wants_json():
            return jsonify({"code": e.code, "message": e.message,
                            "correlation_id": getattr(g, "correlation_id", None)}), e.status
        if e.status in (403, 404):
            return render_template("error.html", status=e.status, message=e.message), e.status
        flash(e.message, "danger")
        return redirect(request.referrer or "/")

    @app.errorhandler(404)
    def _nf(e):
        return render_template("error.html", status=404, message="Page not found"), 404


def enable_rls() -> int:
    """Enable Postgres row level security on every table (Supabase exposes tables through its API).

    The app connects as the table owner, which RLS does not restrict. Returns the number of tables; 0 elsewhere.
    """
    if db.engine.dialect.name != "postgresql":
        return 0
    quote = db.engine.dialect.identifier_preparer.quote
    tables = db.metadata.sorted_tables
    with db.engine.begin() as conn:
        for t in tables:
            conn.execute(text(f"ALTER TABLE {quote(t.name)} ENABLE ROW LEVEL SECURITY"))
    return len(tables)


def drop_everything() -> None:
    """Drop every table, including leftovers of earlier schemas that no model describes."""
    if db.engine.dialect.name != "postgresql":
        db.drop_all()
        return
    quote = db.engine.dialect.identifier_preparer.quote
    names = inspect(db.engine).get_table_names(schema="public")
    with db.engine.begin() as conn:
        for name in names:
            conn.execute(text(f"DROP TABLE IF EXISTS {quote(name)} CASCADE"))


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    @click.option("--reset", is_flag=True, help="Drop every table first, then recreate and reseed.")
    def init_db_cmd(reset: bool):
        """Create the 8-table schema and seed the Tiki.vn catalogue with demo customers."""
        from . import seed_tiki
        from .modules.identity.models import Customer
        if reset:
            drop_everything()
        elif inspect(db.engine).has_table("Customer") and db.session.query(Customer.id).first() is not None:
            click.echo("Database already initialised; use --reset to wipe and reseed.")
            raise SystemExit(1)
        db.create_all()
        counts = seed_tiki.run()
        db.session.commit()
        db.session.close()
        rls = enable_rls()
        for k, v in counts.items():
            click.echo(f"{k}: {v}")
        if rls:
            click.echo(f"row level security enabled on {rls} tables")
