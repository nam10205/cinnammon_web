from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request

from ... import auth
from ...errors import NotFound, ValidationError
from ...extensions import db
from . import service

bp = Blueprint("identity", __name__)

STAFF_HOME = {"seller": "/seller/products", "admin": "/admin"}


def _safe_next() -> str | None:
    n = request.values.get("next", "")
    return n if n.startswith("/") and not n.startswith("//") and "\\" not in n else None


def _after_login(role: str):
    return redirect(_safe_next() or STAFF_HOME.get(role, "/"))


@bp.get("/login")
def login():
    return render_template("auth/login.html", next=_safe_next())


@bp.post("/login/quick/<who>")
def login_quick(who):
    if who == "customer":
        c = service.find_by_email(service.QUICK_CUSTOMER_EMAIL)
        if c is None:
            flash("Demo customer not found — run init-db", "danger")
            return redirect("/login")
        auth.login_customer(c)
    elif who in ("seller", "admin"):
        auth.login_staff(who)
    else:
        raise NotFound("Unknown login")
    return _after_login(who)


@bp.post("/login/email")
def login_email():
    c = service.find_by_email(request.form.get("email", ""))
    if c is None:
        flash("No customer with that email", "danger")
        return redirect("/login")
    auth.login_customer(c)
    return _after_login("customer")


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    form = request.form
    if request.method == "POST":
        try:
            c = service.signup(form.get("first_name"), form.get("middle_name"), form.get("last_name"),
                               form.get("email"), form.get("phone"), form.get("ward"), form.get("street"),
                               form.get("detail"))
        except ValidationError as e:
            db.session.rollback()
            flash(e.message, "danger")
            return render_template("auth/signup.html", form=form), 400
        auth.login_customer(c)
        return _after_login("customer")
    return render_template("auth/signup.html", form={})


@bp.post("/logout")
def logout():
    auth.logout()
    return redirect("/")


@bp.route("/profile", methods=["GET", "POST"])
@auth.require_role("customer")
def profile():
    c = auth.current_customer()
    if request.method == "POST":
        f = request.form
        try:
            service.update_profile(c, f.get("first_name"), f.get("middle_name"), f.get("last_name"),
                                   f.get("phone"), f.get("ward"), f.get("street"), f.get("detail"))
        except ValidationError as e:
            db.session.rollback()
            flash(e.message, "danger")
            return render_template("customer/profile.html", c=c, form=f), 400
        flash("Profile saved", "success")
        return redirect("/profile")
    n, a = c.full_name, c.address
    form = {"first_name": n.first_name, "middle_name": n.middle_name, "last_name": n.last_name,
            "phone": c.phone_number, "ward": a.ward, "street": a.street, "detail": a.detail} if n and a else {}
    return render_template("customer/profile.html", c=c, form=form)
