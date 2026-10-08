from __future__ import annotations

from ...extensions import db


class PlatformPolicy(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(500), nullable=False)


class Clock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offset_hours = db.Column(db.Integer, default=0, nullable=False)
