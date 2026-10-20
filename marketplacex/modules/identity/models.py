from __future__ import annotations

from datetime import datetime

from ...extensions import db

ROLES = ("customer", "seller", "admin")


class Account(db.Model):
    """Login for every role. Customers additionally own an ERD ``Customer`` row."""
    __tablename__ = "account"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    status = db.Column(db.String(20), nullable=False, default="active")
    phone = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer", back_populates="account", uselist=False)

    @property
    def addresses(self) -> list[Address]:
        return self.customer.addresses if self.customer else []


class FullName(db.Model):
    __tablename__ = "FullName"
    id = db.Column("fullNameID", db.Integer, primary_key=True)
    first_name = db.Column("firstName", db.String(255))
    middle_name = db.Column("middleName", db.String(255))
    last_name = db.Column("lastName", db.String(255))

    @property
    def display(self) -> str:
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)


class Customer(db.Model):
    __tablename__ = "Customer"
    id = db.Column("customerID", db.Integer, primary_key=True)
    full_name_id = db.Column("fullNameID", db.Integer, db.ForeignKey("FullName.fullNameID"))
    # Circular with Address.customerID: added by ALTER after both tables exist.
    address_id = db.Column("addressID", db.Integer,
                           db.ForeignKey("Address.addressID", use_alter=True, name="fk_customer_default_address"),
                           nullable=True)
    email = db.Column("email", db.String(255))
    phone_number = db.Column("phoneNumber", db.String(255))
    account_id = db.Column("accountID", db.Integer, db.ForeignKey("account.id"), unique=True, nullable=False)

    full_name = db.relationship("FullName")
    account = db.relationship("Account", back_populates="customer")
    addresses = db.relationship("Address", foreign_keys="Address.customer_id", back_populates="customer",
                                order_by="Address.id")
    default_address = db.relationship("Address", foreign_keys=[address_id], post_update=True)


class Address(db.Model):
    __tablename__ = "Address"
    id = db.Column("addressID", db.Integer, primary_key=True)
    ward = db.Column("ward", db.String(255))
    street = db.Column("street", db.String(255))
    detail = db.Column("detail", db.String(255))
    customer_id = db.Column("customerID", db.Integer, db.ForeignKey("Customer.customerID"), nullable=False)
    recipient = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(255), nullable=False)
    district = db.Column(db.String(255))
    city = db.Column(db.String(255), nullable=False)
    is_default = db.Column("isDefault", db.Boolean, default=False)

    customer = db.relationship("Customer", foreign_keys=[customer_id], back_populates="addresses")

    @property
    def line(self) -> str:
        return ", ".join(p for p in (self.detail, self.street, self.ward, self.district) if p)

    def as_dict(self) -> dict:
        return {"recipient": self.recipient, "phone": self.phone, "line": self.line, "city": self.city,
                "ward": self.ward, "street": self.street, "district": self.district}


class PasswordResetToken(db.Model):
    token = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
