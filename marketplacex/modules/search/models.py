from __future__ import annotations

from ...extensions import db


class SearchTrace(db.Model):
    """Query trace kept for offline diagnosis and the zero-result metric (report §4.1, §4.5)."""
    id = db.Column(db.Integer, primary_key=True)
    trace_id = db.Column(db.String(32), unique=True, nullable=False)
    customer_id = db.Column(db.Integer)
    query_json = db.Column(db.JSON)
    result_count = db.Column(db.Integer, nullable=False)
    degraded = db.Column(db.Boolean, default=False)
    at = db.Column(db.DateTime, nullable=False)
