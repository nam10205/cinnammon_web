"""Administrator use cases: taxonomy, campaigns, policy, governance (FR26, FR27, report §4.4)."""
from __future__ import annotations

import uuid
from datetime import timedelta

from ...errors import NotFound, ValidationError
from ...extensions import db
from ..audit import service as audit
from . import policy


def _reason(reason: str) -> str:
    if not (reason or "").strip():
        raise ValidationError("Reason is required")
    return reason.strip()


def save_category(actor, data: dict, category_id: int | None = None):
    from ..catalog.models import Category
    reason = _reason(data.get("reason"))
    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("Category name is required")
    schema = data.get("attribute_schema") or []
    if isinstance(schema, str):
        schema = [s.strip() for s in schema.split(",") if s.strip()]
    c = db.session.get(Category, category_id) if category_id else Category()
    if c is None:
        raise NotFound("Category not found")
    c.name = name
    c.parent_id = int(data["parent_id"]) if data.get("parent_id") else None
    c.attribute_schema = schema
    if category_id is None:
        db.session.add(c)
    db.session.flush()
    audit.record(actor, "category.save", "category", c.id, reason)
    db.session.commit()
    return c


def delete_category(actor, category_id: int, reason: str) -> None:
    from ..catalog.models import Category, Product
    reason = _reason(reason)
    c = db.session.get(Category, category_id)
    if c is None:
        raise NotFound("Category not found")
    if Product.query.filter_by(category_id=c.id).first() or c.children:
        raise ValidationError("Category has products or sub-categories; historical listings keep its schema")
    audit.record(actor, "category.delete", "category", c.id, reason)
    db.session.delete(c)
    db.session.commit()


def save_campaign(actor, data: dict, campaign_id: int | None = None):
    from ..promotion.models import Campaign
    reason = _reason(data.get("reason"))
    c = db.session.get(Campaign, campaign_id) if campaign_id else Campaign(spent_vnd=0)
    if c is None:
        raise NotFound("Campaign not found")
    c.name = (data.get("name") or "").strip() or "Campaign"
    c.budget_vnd = int(data.get("budget_vnd") or 0)
    if campaign_id is None:
        c.starts_at = policy.now()
        c.ends_at = policy.now() + timedelta(days=int(data.get("days") or 7))
        db.session.add(c)
    c.active = str(data.get("active", "1")) not in ("0", "false", "")
    db.session.flush()
    audit.record(actor, "campaign.save", "campaign", c.id, reason)
    db.session.commit()
    return c


def save_voucher(actor, data: dict, voucher_id: int | None = None):
    from ..promotion.models import Voucher
    reason = _reason(data.get("reason"))
    code = (data.get("code") or "").strip().upper()
    if not code or data.get("kind") not in ("percent", "fixed", "free_shipping"):
        raise ValidationError("Voucher code and a valid type are required")
    v = db.session.get(Voucher, voucher_id) if voucher_id else Voucher(used_count=0)
    if v is None:
        raise NotFound("Voucher not found")
    if Voucher.query.filter(Voucher.code == code, Voucher.id != (voucher_id or 0)).first():
        raise ValidationError("Voucher code already exists")
    v.campaign_id = int(data["campaign_id"])
    v.code = code
    v.kind = data["kind"]
    v.value = int(data.get("value") or 0)
    v.min_spend_vnd = int(data.get("min_spend_vnd") or 0)
    v.max_discount_vnd = int(data["max_discount_vnd"]) if str(data.get("max_discount_vnd") or "").strip() else None
    v.usage_limit = int(data.get("usage_limit") or 100)
    v.shop_id = int(data["shop_id"]) if str(data.get("shop_id") or "").strip() else None
    if voucher_id is None:
        db.session.add(v)
    db.session.flush()
    audit.record(actor, "voucher.save", "voucher", v.id, reason)
    db.session.commit()
    return v


def set_policy(actor, key: str, value: str, reason: str) -> None:
    _reason(reason)
    if key not in policy.DEFAULTS:
        raise ValidationError("Unknown policy key")
    if key != "prohibited_terms":
        try:
            if int(value) < 0:
                raise ValueError
        except ValueError:
            raise ValidationError("Value must be a non-negative whole number")
    policy.set_value(key, value, actor)


def moderate_listing(actor, product_id: int, approve: bool, reason: str):
    from ..catalog import service as catalog
    reason = _reason(reason)
    p = catalog.get_product(product_id)
    return catalog.set_status(p, "active" if approve else "rejected", actor, reason)


def suspend_listing(actor, product_id: int, reason: str):
    from ..catalog import service as catalog
    return catalog.set_status(catalog.get_product(product_id), "suspended", actor, _reason(reason))


def bulk_moderate_preview(product_ids: list[int]) -> list:
    from ..catalog.models import Product
    return Product.query.filter(Product.id.in_(product_ids)).order_by(Product.id).all()


def bulk_moderate(actor, product_ids: list[int], approve: bool, reason: str) -> dict:
    reason = _reason(reason)
    job_id = uuid.uuid4().hex[:10]
    done, failed = 0, 0
    for pid in product_ids:
        try:
            moderate_listing(actor, pid, approve, f"[bulk {job_id}] {reason}")
            done += 1
        except Exception:  # recorded in the job result; one bad id must not abort the batch
            db.session.rollback()
            failed += 1
    audit.record(actor, "listing.bulk_moderate", "job", job_id, f"{reason} ({done} done, {failed} failed)")
    db.session.commit()
    return {"job_id": job_id, "done": done, "failed": failed}


def verify_shop(actor, shop_id: int, approve: bool, reason: str):
    from ..seller.models import Shop
    reason = _reason(reason)
    s = db.session.get(Shop, shop_id)
    if s is None:
        raise NotFound("Shop not found")
    before = s.verification_status
    s.verification_status = "verified" if approve else "rejected"
    audit.record(actor, "shop.verify" if approve else "shop.reject", "shop", s.id, reason,
                 {"status": before}, {"status": s.verification_status})
    db.session.commit()
    return s


def suspend_user(actor, user_id: int, suspend: bool, reason: str):
    from ..identity.models import Account
    reason = _reason(reason)
    u = db.session.get(Account, user_id)
    if u is None:
        raise NotFound("User not found")
    if u.id == actor.id:
        raise ValidationError("You cannot suspend yourself")
    before = u.status
    u.status = "suspended" if suspend else "active"
    audit.record(actor, "user.suspend" if suspend else "user.reinstate", "user", u.id, reason,
                 {"status": before}, {"status": u.status})
    db.session.commit()
    return u


def set_review_hidden(actor, review_id: int, hidden: bool, reason: str):
    from ..review import service as review
    return review.set_hidden(actor, review_id, hidden, reason)


def run_settlement(actor) -> int:
    from ..settlement import service as settlement
    n = settlement.release_eligible(actor)
    audit.record(actor, "settlement.release", "settlement", "batch", f"{n} orders released")
    db.session.commit()
    return n


def advance_clock(actor, hours: int, reason: str = "demo fast-forward") -> None:
    audit.record(actor, "clock.advance", "clock", 1, f"{reason}: +{int(hours)}h")
    policy.advance_clock(int(hours))
