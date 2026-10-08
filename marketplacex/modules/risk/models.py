from __future__ import annotations

from ...extensions import db


class RiskAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(20), nullable=False)  # checkout | refund | account
    target_id = db.Column(db.Integer, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    rule = db.Column(db.String(40), nullable=False)
    score = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default="open")  # open|held|released|dismissed|rejected
    context = db.Column(db.JSON, default=dict)
    decided_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False)
    customer = db.relationship("User", foreign_keys=[customer_id])
    analyst = db.relationship("User", foreign_keys=[decided_by])
