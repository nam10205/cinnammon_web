from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, login_user, logout_user, require_role
from ...errors import NotFound, ValidationError
from . import service
from .models import ROLES, User

bp = Blueprint("identity", __name__)

HOME_BY_ROLE = {"customer": "/", "seller": "/seller/", "admin": "/admin/", "support": "/support/", "risk": "/risk/"}


def _home_for(user) -> str:
    return HOME_BY_ROLE.get(user.role, "/")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            u = service.authenticate(request.form.get("email"), request.form.get("password"))
        except ValidationError as e:
            flash(e.message, "danger")
            return render_template("auth/login.html", roles=ROLES), 400
        login_user(u)
        flash(f"Welcome back, {u.name}", "success")
        return redirect(request.args.get("next") or _home_for(u))
    return render_template("auth/login.html", roles=ROLES)


@bp.post("/demo-login/<role>")
def demo_login(role):
    u = User.query.filter_by(role=role, status="active").order_by(User.id).first()
    if u is None:
        raise NotFound(f"No demo {role} account. Run `flask --app marketplacex.app seed`.")
    login_user(u)
    flash(f"Logged in as {u.name} ({role})", "success")
    return redirect(_home_for(u))


@bp.get("/logout")
def logout():
    logout_user()
    return redirect(url_for("identity.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = service.register(request.form.get("email"), request.form.get("password"), request.form.get("name"))
        login_user(u)
        flash("Account created", "success")
        return redirect("/")
    return render_template("auth/register.html")


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    link = None
    if request.method == "POST":
        tok = service.start_recovery(request.form.get("email"))
        flash("If the account exists, a recovery email has been sent.", "info")
        if tok:
            link = url_for("identity.reset", token=tok)  # dev mode: show the emailed link
    return render_template("auth/forgot.html", link=link)


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    if request.method == "POST":
        service.reset_password(token, request.form.get("password"))
        flash("Password updated. Please sign in.", "success")
        return redirect(url_for("identity.login"))
    return render_template("auth/reset.html", token=token)


@bp.get("/account")
@require_role()
def account():
    return render_template("auth/account.html", user=current_user())


@bp.post("/account/addresses")
@require_role()
def add_address():
    f = request.form
    service.add_address(current_user(), f.get("recipient"), f.get("phone"), f.get("line"), f.get("city"),
                        bool(f.get("is_default")))
    flash("Address saved", "success")
    return redirect(url_for("identity.account"))
