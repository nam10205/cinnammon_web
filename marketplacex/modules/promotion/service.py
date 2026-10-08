"""Promotion: evaluate vouchers, reserve/commit/release redemptions against an atomic budget (report §7, §12.4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func

from ...errors import NotFound, VoucherExhausted, VoucherInvalid
from ...extensions import db
from ..admin import policy
from .models import Campaign, Redemption, Voucher


@dataclass
class Applied:
    voucher_id: int
    code: str
    campaign_id: int
    shop_id: int | None
    amount_vnd: int
    kind: str


@dataclass
class Evaluation:
    applied: list = field(default_factory=list)
    item_discounts: dict = field(default_factory=dict)       # shop_id -> total item discount
    shop_discounts: dict = field(default_factory=dict)       # shop_id -> seller-funded discount
    platform_discounts: dict = field(default_factory=dict)   # shop_id -> platform-funded item discount
    shipping_discounts: dict = field(default_factory=dict)   # shop_id -> shipping discount


def _active_holds(voucher_id: int):
    now = policy.now()
    q = Redemption.query.filter(Redemption.voucher_id == voucher_id, Redemption.status == "held",
                                (Redemption.expires_at.is_(None)) | (Redemption.expires_at > now))
    return q


def _check_available(v: Voucher, amount: int) -> None:
    held = _active_holds(v.id)
    if v.used_count + held.count() >= v.usage_limit:
        raise VoucherExhausted(f"Voucher {v.code} is fully redeemed")
    held_amount = db.session.query(func.coalesce(func.sum(Redemption.amount_vnd), 0)).filter(
        Redemption.campaign_id == v.campaign_id, Redemption.status == "held",
        (Redemption.expires_at.is_(None)) | (Redemption.expires_at > policy.now())).scalar()
    c = v.campaign
    if c.spent_vnd + held_amount + amount > c.budget_vnd:
        raise VoucherExhausted(f"Campaign budget for {v.code} is exhausted")


def _lookup(code: str) -> Voucher:
    v = Voucher.query.filter(func.upper(Voucher.code) == code.strip().upper()).first()
    now = policy.now()
    if v is None or not v.campaign.active or not (v.campaign.starts_at <= now <= v.campaign.ends_at):
        raise VoucherInvalid(f"Voucher {code} is not valid")
    return v


def _split(amount: int, weights: dict[int, int]) -> dict[int, int]:
    total = sum(weights.values())
    if total <= 0 or amount <= 0:
        return {k: 0 for k in weights}
    out = {k: amount * w // total for k, w in weights.items()}
    largest = max(weights, key=lambda k: (weights[k], -k))
    out[largest] += amount - sum(out.values())
    return out


def evaluate(customer, shop_subtotals: dict[int, int], shipping: dict[int, int], codes: list[str]) -> Evaluation:
    ev = Evaluation(item_discounts={s: 0 for s in shop_subtotals}, shop_discounts={s: 0 for s in shop_subtotals},
                    platform_discounts={s: 0 for s in shop_subtotals},
                    shipping_discounts={s: 0 for s in shop_subtotals})
    codes = [c for c in dict.fromkeys((c or "").strip().upper() for c in codes) if c]
    vouchers = [_lookup(c) for c in codes]
    platform = [v for v in vouchers if v.shop_id is None]
    if len(platform) > 1:
        raise VoucherInvalid("Only one platform voucher can be used per checkout")
    seen_shops = set()
    for v in [v for v in vouchers if v.shop_id is not None]:
        if v.shop_id in seen_shops:
            raise VoucherInvalid("Only one voucher per shop")
        seen_shops.add(v.shop_id)
        sub = shop_subtotals.get(v.shop_id)
        if sub is None:
            raise VoucherInvalid(f"Voucher {v.code} only applies to {v.shop.name}")
        if sub < v.min_spend_vnd:
            raise VoucherInvalid(f"Voucher {v.code} needs a minimum spend of {v.min_spend_vnd:,} ₫ at {v.shop.name}")
        if v.kind == "free_shipping":
            amt = min(shipping.get(v.shop_id, 0), v.max_discount_vnd or shipping.get(v.shop_id, 0))
            ev.shipping_discounts[v.shop_id] += amt
        else:
            amt = min(sub, v.value if v.kind == "fixed" else sub * v.value // 100)
            if v.max_discount_vnd:
                amt = min(amt, v.max_discount_vnd)
            ev.shop_discounts[v.shop_id] += amt
        _check_available(v, amt)
        ev.applied.append(Applied(v.id, v.code, v.campaign_id, v.shop_id, amt, v.kind))
    for v in platform:
        total = sum(shop_subtotals.values())
        if total < v.min_spend_vnd:
            raise VoucherInvalid(f"Voucher {v.code} needs a minimum spend of {v.min_spend_vnd:,} ₫")
        if v.kind == "free_shipping":
            ship_total = sum(shipping.values())
            amt = min(ship_total, v.max_discount_vnd or ship_total)
            for s, a in _split(amt, shipping).items():
                ev.shipping_discounts[s] += a
        else:
            remaining = {s: shop_subtotals[s] - ev.shop_discounts[s] for s in shop_subtotals}
            amt = min(sum(remaining.values()), v.value if v.kind == "fixed" else total * v.value // 100)
            if v.max_discount_vnd:
                amt = min(amt, v.max_discount_vnd)
            for s, a in _split(amt, remaining).items():
                ev.platform_discounts[s] += a
        _check_available(v, amt)
        ev.applied.append(Applied(v.id, v.code, v.campaign_id, None, amt, v.kind))
    for s in shop_subtotals:
        ev.item_discounts[s] = ev.shop_discounts[s] + ev.platform_discounts[s]
    return ev


def reserve(customer, applied: list, attempt_id: str, ttl_min: int) -> list[Redemption]:
    existing = Redemption.query.filter_by(attempt_id=attempt_id, customer_id=customer.id).all()
    if existing:
        return existing
    out = []
    now = policy.now()
    for a in applied:
        a = a if isinstance(a, Applied) else Applied(**a)
        v = db.session.get(Voucher, a.voucher_id)
        _check_available(v, a.amount_vnd)
        r = Redemption(voucher_id=a.voucher_id, customer_id=customer.id, campaign_id=a.campaign_id,
                       attempt_id=attempt_id, amount_vnd=a.amount_vnd, status="held",
                       expires_at=now + timedelta(minutes=ttl_min), created_at=now)
        db.session.add(r)
        out.append(r)
    db.session.commit()
    return out


def commit(attempt_id: str, group_id: int) -> None:
    for r in Redemption.query.filter_by(attempt_id=attempt_id, status="held").all():
        r.status = "committed"
        r.order_group_id = group_id
        r.voucher.used_count += 1
        r.voucher.campaign.spent_vnd += r.amount_vnd
    db.session.commit()


def release(attempt_id: str) -> None:
    for r in Redemption.query.filter_by(attempt_id=attempt_id, status="held").all():
        r.status = "released"
    db.session.commit()


def active_campaigns() -> list[Campaign]:
    now = policy.now()
    return Campaign.query.filter(Campaign.active.is_(True), Campaign.starts_at <= now, Campaign.ends_at >= now).all()


def get_campaign(campaign_id: int) -> Campaign:
    c = db.session.get(Campaign, campaign_id)
    if c is None:
        raise NotFound("Campaign not found")
    return c


def eligible_offers(campaign: Campaign) -> list:
    from ..catalog import service as catalog
    if any(v.shop_id is None for v in campaign.vouchers):
        return catalog.popular_offers(24)
    out = []
    for v in campaign.vouchers:
        out.extend(catalog.offers_of_shop(v.shop_id))
    return out


def extend_hold(attempt_id: str, minutes: int) -> None:
    until = policy.now() + timedelta(minutes=minutes)
    for r in Redemption.query.filter_by(attempt_id=attempt_id, status="held").all():
        r.expires_at = max(r.expires_at or until, until)
    db.session.commit()
