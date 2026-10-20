from __future__ import annotations

from datetime import datetime

from ...extensions import db

ROLES = ("customer", "seller", "admin")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    status = db.Column(db.String(20), nullable=False, default="active")
    phone = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    addresses = db.relationship("Address", backref="user", order_by="Address.id")


class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipient = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    line = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    is_default = db.Column(db.Boolean, default=False)

    def as_dict(self) -> dict:
        return {"recipient": self.recipient, "phone": self.phone, "line": self.line, "city": self.city}


class PasswordResetToken(db.Model):
    token = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
