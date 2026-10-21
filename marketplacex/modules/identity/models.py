from __future__ import annotations

from ...extensions import db


class FullName(db.Model):
    __tablename__ = "FullName"
    id = db.Column("fullNameID", db.Integer, primary_key=True)
    first_name = db.Column("firstName", db.String(255))
    middle_name = db.Column("middleName", db.String(255))
    last_name = db.Column("lastName", db.String(255))

    @property
    def display(self) -> str:
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)


class Address(db.Model):
    __tablename__ = "Address"
    id = db.Column("addressID", db.Integer, primary_key=True)
    ward = db.Column("ward", db.String(255))
    street = db.Column("street", db.String(255))
    detail = db.Column("detail", db.String(255))

    @property
    def line(self) -> str:
        return ", ".join(p for p in (self.detail, self.street, self.ward) if p)


class Customer(db.Model):
    __tablename__ = "Customer"
    id = db.Column("customerID", db.Integer, primary_key=True)
    full_name_id = db.Column("fullNameID", db.Integer, db.ForeignKey("FullName.fullNameID"))
    address_id = db.Column("addressID", db.Integer, db.ForeignKey("Address.addressID"))
    email = db.Column("email", db.String(255), unique=True, nullable=False)
    phone_number = db.Column("phoneNumber", db.String(255))

    full_name = db.relationship("FullName")
    address = db.relationship("Address")

    @property
    def name(self) -> str:
        return self.full_name.display if self.full_name else ""
