from __future__ import annotations

from ...extensions import db


class ReturnCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    remedy = db.Column(db.String(30), nullable=False)  # refund_only | return_and_refund
    status = db.Column(db.String(30), nullable=False, default="requested")
    seller_response = db.Column(db.String(500))
    seller_deadline = db.Column(db.DateTime)
    proposed_amount_vnd = db.Column(db.Integer)
    inspection_result = db.Column(db.String(300))
    refund_amount_vnd = db.Column(db.Integer)
    created_at = db.Column(db.DateTime)
    order = db.relationship("Order")
    customer = db.relationship("Account")
    items = db.relationship("ReturnCaseItem", cascade="all, delete-orphan")
    evidence = db.relationship("Evidence", order_by="Evidence.id")
    decision = db.relationship("DisputeDecision", uselist=False)


class ReturnCaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("return_case.id"), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_item.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    order_item = db.relationship("OrderItem")


class Evidence(db.Model):
    """Append-only case timeline: statements, images and system events."""
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("return_case.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("account.id"))
    kind = db.Column(db.String(10), nullable=False)  # statement | image | system
    content = db.Column(db.String(1000), nullable=False)
    at = db.Column(db.DateTime, nullable=False)
    author = db.relationship("Account")


class DisputeDecision(db.Model):
    """Immutable, reason-coded platform decision (FR18)."""
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("return_case.id"), unique=True, nullable=False)
    decided_by = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    reason_code = db.Column(db.String(40), nullable=False)
    outcome = db.Column(db.String(30), nullable=False)  # refund_customer | side_with_seller | partial
    amount_vnd = db.Column(db.Integer)
    note = db.Column(db.String(1000))
    at = db.Column(db.DateTime, nullable=False)
    agent = db.relationship("Account")
