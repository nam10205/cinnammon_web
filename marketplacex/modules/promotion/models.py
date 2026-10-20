from __future__ import annotations

from ...extensions import db


class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    budget_vnd = db.Column(db.Integer, nullable=False, default=0)
    spent_vnd = db.Column(db.Integer, nullable=False, default=0)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    vouchers = db.relationship("Voucher", backref="campaign", order_by="Voucher.id")


class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaign.id"), nullable=False)
    code = db.Column(db.String(40), unique=True, nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # percent | fixed | free_shipping
    value = db.Column(db.Integer, nullable=False, default=0)
    min_spend_vnd = db.Column(db.Integer, nullable=False, default=0)
    max_discount_vnd = db.Column(db.Integer)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"))  # None = platform voucher
    usage_limit = db.Column(db.Integer, nullable=False, default=100)
    used_count = db.Column(db.Integer, nullable=False, default=0)
    shop = db.relationship("Shop")

    def describe(self) -> str:
        if self.kind == "percent":
            s = f"{self.value}% off"
            if self.max_discount_vnd:
                s += f" (max {self.max_discount_vnd:,} ₫)"
        elif self.kind == "fixed":
            s = f"{self.value:,} ₫ off"
        else:
            s = "Free shipping" + (f" up to {self.max_discount_vnd:,} ₫" if self.max_discount_vnd else "")
        if self.min_spend_vnd:
            s += f", min spend {self.min_spend_vnd:,} ₫"
        return s


class Redemption(db.Model):
    """Voucher hold/redemption; key unique per customer, campaign and checkout attempt (BR04)."""
    id = db.Column(db.Integer, primary_key=True)
    voucher_id = db.Column(db.Integer, db.ForeignKey("voucher.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaign.id"), nullable=False)
    attempt_id = db.Column(db.String(64), nullable=False, index=True)
    order_group_id = db.Column(db.Integer)
    amount_vnd = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="held")
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime)
    voucher = db.relationship("Voucher")
    __table_args__ = (db.UniqueConstraint("customer_id", "campaign_id", "attempt_id", "voucher_id"),)
