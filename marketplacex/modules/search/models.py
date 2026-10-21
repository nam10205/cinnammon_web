from __future__ import annotations

from ...extensions import db


class SearchHistory(db.Model):
    """A customer's past search: text, voice or image (ERD SearchHistory)."""
    __tablename__ = "SearchHistory"
    id = db.Column("searchHistoryID", db.Integer, primary_key=True)
    customer_id = db.Column("customerID", db.Integer, db.ForeignKey("Customer.customerID"), nullable=False)
    keyword = db.Column("keyword", db.String(255), nullable=False)
    search_type = db.Column("searchType", db.String(255), nullable=False, default="text")  # text | voice | image
    searched_at = db.Column("searchedAt", db.DateTime, nullable=False)
