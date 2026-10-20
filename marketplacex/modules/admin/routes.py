from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from ..audit import service as audit
from . import policy, service

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@require_role("admin")
def dashboard():
    from ..reporting import service as reporting
    return render_template("admin/dashboard.html", r=reporting.summary())


@bp.route("/categories", methods=["GET", "POST"])
@require_role("admin")
def categories():
    from ..catalog import service as catalog
    if request.method == "POST":
        f = request.form
        if f.get("action") == "delete":
            service.delete_category(current_user(), f.get("id", type=int), f.get("reason"))
            flash("Category deleted", "success")
        else:
            service.save_category(current_user(), f.to_dict(), f.get("id", type=int))
            flash("Category saved", "success")
        return redirect(url_for("admin.categories"))
    return render_template("admin/categories.html", tree=catalog.category_tree())


@bp.route("/campaigns", methods=["GET", "POST"])
@require_role("admin")
def campaigns():
    from ..promotion.models import Campaign
    from ..seller.models import Shop
    if request.method == "POST":
        f = request.form
        if f.get("action") == "voucher":
            service.save_voucher(current_user(), f.to_dict(), f.get("id", type=int))
            flash("Voucher saved", "success")
        else:
            service.save_campaign(current_user(), f.to_dict(), f.get("id", type=int))
            flash("Campaign saved", "success")
        return redirect(url_for("admin.campaigns"))
    return render_template("admin/campaigns.html", campaigns=Campaign.query.order_by(Campaign.id.desc()).all(),
                           shops=Shop.query.order_by(Shop.name).all())


@bp.route("/policy", methods=["GET", "POST"])
@require_role("admin")
def policy_page():
    if request.method == "POST":
        f = request.form
        action = f.get("action")
        if action == "clock":
            service.advance_clock(current_user(), f.get("hours", type=int) or 0)
            flash(f"Clock advanced by {f.get('hours')} hours", "info")
        elif action == "reset_clock":
            audit.record(current_user(), "clock.reset", "clock", 1, "demo reset")
            policy.reset_clock()
            flash("Clock reset", "info")
        elif action == "settlement":
            n = service.run_settlement(current_user())
            flash(f"{n} order(s) completed and settlement released", "success")
        else:
            service.set_policy(current_user(), f.get("key"), f.get("value"), f.get("reason"))
            flash("Policy updated", "success")
        return redirect(url_for("admin.policy_page"))
    return render_template("admin/policy.html", values=policy.all_values(), now=policy.now(),
                           offset=policy.clock_offset_hours())


@bp.route("/moderation", methods=["GET", "POST"])
@require_role("admin")
def moderation():
    from ..catalog import service as catalog
    from ..review import service as review
    from ..seller.models import Shop
    if request.method == "POST":
        f = request.form
        kind, u = f.get("kind"), current_user()
        if kind == "listing":
            service.moderate_listing(u, f.get("id", type=int), f.get("approve") == "1", f.get("reason"))
        elif kind == "shop":
            service.verify_shop(u, f.get("id", type=int), f.get("approve") == "1", f.get("reason"))
        elif kind == "review":
            service.set_review_hidden(u, f.get("id", type=int), f.get("hide") == "1", f.get("reason"))
        elif kind == "suspend_listing":
            service.suspend_listing(u, f.get("id", type=int), f.get("reason"))
        elif kind == "bulk":
            ids = [int(x) for x in f.getlist("ids")]
            if f.get("confirm") != "1":
                return render_template("admin/bulk_confirm.html", products=service.bulk_moderate_preview(ids),
                                       approve=f.get("approve"), reason=f.get("reason"))
            job = service.bulk_moderate(u, ids, f.get("approve") == "1", f.get("reason"))
            flash(f"Bulk job {job['job_id']}: {job['done']} done, {job['failed']} failed", "info")
            return redirect(url_for("admin.moderation"))
        flash("Decision recorded", "success")
        return redirect(url_for("admin.moderation"))
    from ..catalog.models import Product
    return render_template("admin/moderation.html", pending=catalog.pending_products(),
                           shops=Shop.query.filter_by(verification_status="pending").all(),
                           reviews=review.low_rated(), active=Product.query.filter_by(status="active").order_by(Product.id).all())


@bp.route("/users", methods=["GET", "POST"])
@require_role("admin")
def users():
    from ..identity.models import Account
    if request.method == "POST":
        f = request.form
        service.suspend_user(current_user(), f.get("id", type=int), f.get("suspend") == "1", f.get("reason"))
        flash("User updated", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/users.html", users=Account.query.order_by(Account.id).all())


@bp.get("/audit")
@require_role("admin")
def audit_log():
    return render_template("admin/audit.html", events=audit.latest(200))
