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


class SearchHistory(db.Model):
    """A customer's past search, text or image (ERD SearchHistory)."""
    __tablename__ = "SearchHistory"
    id = db.Column("searchHistoryID", db.Integer, primary_key=True)
    customer_id = db.Column("customerID", db.Integer, db.ForeignKey("Customer.customerID"), nullable=False)
    keyword = db.Column("keyword", db.String(255), nullable=False)
    search_type = db.Column("searchType", db.String(255), nullable=False, default="text")  # text | image
    searched_at = db.Column("searchedAt", db.DateTime, nullable=False)
