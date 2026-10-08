"""MarketplaceX application factory: a modular monolith (report §15)."""
from __future__ import annotations

import importlib
import os
import uuid

from flask import Flask, flash, g, jsonify, redirect, render_template, request

from .config import Config
from .errors import DomainError
from .extensions import db

# One package per service in the report's component diagram (Figure 2).
MODULES = [
    "admin", "audit", "identity", "seller", "catalog", "inventory", "search", "cart", "promotion",
    "order", "payment", "logistics", "checkout", "notification", "review", "returns", "settlement",
    "reporting", "support", "risk", "chat",
]


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
    os.makedirs(os.path.join(os.path.dirname(app.root_path), "instance"), exist_ok=True)
    db.init_app(app)

    from . import events  # noqa: F401  (registers EventLog models)
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
    from .auth import current_user

    @app.before_request
    def _correlation():
        g.correlation_id = uuid.uuid4().hex
        g.pop("current_user", None)

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
        u = current_user()
        unread = 0
        if u is not None:
            try:
                from .modules.notification import service as notif
                unread = notif.unread_count(u)
            except ImportError:
                unread = 0
        return {"current_user": u, "has_endpoint": has_endpoint, "unread_count": unread}


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


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed_cmd():
        """Drop, recreate and seed the demo database."""
        from . import seed
        db.drop_all()
        db.create_all()
        seed.run()
        print("Seeded demo data.")

