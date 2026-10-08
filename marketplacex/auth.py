from __future__ import annotations

from functools import wraps

from flask import g, redirect, request, session, url_for

from .errors import Forbidden
from .extensions import db


def current_user():
    if "current_user" not in g:
        from .modules.identity.models import User
        uid = session.get("user_id")
        u = db.session.get(User, uid) if uid else None
        if u is not None and u.status != "active":
            u = None
        g.current_user = u
    return g.current_user


def login_user(user) -> None:
    session.clear()
    session["user_id"] = user.id
    g.current_user = user


def logout_user() -> None:
    session.clear()
    g.current_user = None


def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if u is None:
                return redirect(url_for("identity.login", next=request.path))
            if roles and u.role not in roles:
                raise Forbidden("You do not have access to this page")
            return fn(*a, **kw)
        return wrapper
    return deco
