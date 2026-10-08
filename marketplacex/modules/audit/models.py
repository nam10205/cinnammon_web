from __future__ import annotations

from ...extensions import db


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer)
    role = db.Column(db.String(20))
    action = db.Column(db.String(64), index=True, nullable=False)
    target_type = db.Column(db.String(32))
    target_id = db.Column(db.String(64))
    reason = db.Column(db.String(500))
    before_digest = db.Column(db.String(16))
    after_digest = db.Column(db.String(16))
    correlation_id = db.Column(db.String(32))
    at = db.Column(db.DateTime, nullable=False)
