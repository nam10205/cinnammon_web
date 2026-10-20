from __future__ import annotations

from ...extensions import db


class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    location = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(500), default="")
    verification_status = db.Column(db.String(20), nullable=False, default="unverified")
    verification_info = db.Column(db.Text)
    owner = db.relationship("Account")
