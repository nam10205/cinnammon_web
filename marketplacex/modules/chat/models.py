from __future__ import annotations

from ...extensions import db


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    customer = db.relationship("User")
    shop = db.relationship("Shop")
    messages = db.relationship("ChatMessage", order_by="ChatMessage.id")
    __table_args__ = (db.UniqueConstraint("customer_id", "shop_id"),)


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.String(1000), nullable=False)
    at = db.Column(db.DateTime, nullable=False)
    sender = db.relationship("User")
