from __future__ import annotations

from ...extensions import db


class CustomerCase(db.Model):
    __tablename__ = "customer_case"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"))
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")  # open|pending|resolved
    assignee_id = db.Column(db.Integer, db.ForeignKey("account.id"))
    created_at = db.Column(db.DateTime, nullable=False)
    customer = db.relationship("Account", foreign_keys=[customer_id])
    assignee = db.relationship("Account", foreign_keys=[assignee_id])
    order = db.relationship("Order")
    notes = db.relationship("CaseNote", order_by="CaseNote.id")


class CaseNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("customer_case.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    body = db.Column(db.String(2000), nullable=False)
    at = db.Column(db.DateTime, nullable=False)
    author = db.relationship("Account")
