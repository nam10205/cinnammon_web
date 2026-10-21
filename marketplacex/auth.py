from __future__ import annotations

from functools import wraps

from flask import g, redirect, request, session, url_for

from .errors import Forbidden
from .extensions import db


def current_role() -> str | None:
    return session.get("role")


def current_customer():
    if "current_customer" not in g:
        from .modules.identity.models import Customer
        cid = session.get("customer_id") if session.get("role") == "customer" else None
        g.current_customer = db.session.get(Customer, cid) if cid else None
    return g.current_customer


def login_customer(customer) -> None:
    cart = session.get("cart")
    session.clear()
    if cart:
        session["cart"] = cart
    session["role"] = "customer"
    session["customer_id"] = customer.id
    g.current_customer = customer


def login_staff(role: str) -> None:
    if role not in ("seller", "admin"):
        raise ValueError(role)
    session.clear()
    session["role"] = role
    g.current_customer = None


def logout() -> None:
    session.clear()
    g.current_customer = None


def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            role = current_role()
            if role is None:
                return redirect(url_for("identity.login", next=request.path))
            if roles and role not in roles:
                raise Forbidden("You do not have access to this page")
            if role == "customer" and current_customer() is None:
                session.clear()
                return redirect(url_for("identity.login", next=request.path))
            return fn(*a, **kw)
        return wrapper
    return deco
