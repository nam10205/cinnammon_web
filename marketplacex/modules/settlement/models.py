from __future__ import annotations

from ...extensions import db

ACCOUNTS = ("customer_payment", "seller_payable", "platform_fee", "shipping", "voucher_funding", "refund")


class LedgerEntry(db.Model):
    """Double-entry marketplace ledger line (report §12.5)."""
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False, index=True)
    account = db.Column(db.String(20), nullable=False)
    debit_vnd = db.Column(db.Integer, nullable=False, default=0)
    credit_vnd = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(10), nullable=False, default="held")
    entry_group = db.Column(db.String(40), nullable=False)
    memo = db.Column(db.String(200))
    at = db.Column(db.DateTime, nullable=False)
