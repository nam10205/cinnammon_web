from __future__ import annotations

from ...extensions import db


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)
    channel = db.Column(db.String(10), nullable=False, default="in_app")
    template = db.Column(db.String(40), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(200))
    status = db.Column(db.String(10), nullable=False, default="sent")
    created_at = db.Column(db.DateTime, nullable=False)
    read_at = db.Column(db.DateTime)
