from __future__ import annotations

from ...errors import ValidationError
from ...extensions import db
from .models import Address, Customer, FullName

QUICK_CUSTOMER_EMAIL = "alice@demo"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def find_by_email(email: str) -> Customer | None:
    return Customer.query.filter_by(email=normalize_email(email)).first()


def _clean(label: str, value: str | None, required: bool = True) -> str:
    v = (value or "").strip()
    if required and not v:
        raise ValidationError(f"{label} is required")
    if len(v) > 255:
        raise ValidationError(f"{label} is too long")
    return v


def _person_fields(first_name, middle_name, last_name, phone, ward, street, detail) -> dict:
    return dict(
        first=_clean("First name", first_name), middle=_clean("Middle name", middle_name, False),
        last=_clean("Last name", last_name), phone=_clean("Phone", phone),
        ward=_clean("Ward", ward), street=_clean("Street", street), detail=_clean("Detail", detail))


def signup(first_name, middle_name, last_name, email, phone, ward, street, detail) -> Customer:
    email = _clean("Email", normalize_email(email))
    if "@" not in email:
        raise ValidationError("Enter a valid email")
    f = _person_fields(first_name, middle_name, last_name, phone, ward, street, detail)
    if find_by_email(email):
        raise ValidationError("An account with this email already exists")
    customer = Customer(
        email=email, phone_number=f["phone"],
        full_name=FullName(first_name=f["first"], middle_name=f["middle"], last_name=f["last"]),
        address=Address(ward=f["ward"], street=f["street"], detail=f["detail"]))
    db.session.add(customer)
    db.session.commit()
    return customer


def update_profile(customer, first_name, middle_name, last_name, phone, ward, street, detail) -> None:
    f = _person_fields(first_name, middle_name, last_name, phone, ward, street, detail)
    name = customer.full_name
    if name is None:
        name = customer.full_name = FullName()
    name.first_name, name.middle_name, name.last_name = f["first"], f["middle"], f["last"]
    customer.phone_number = f["phone"]
    a = customer.address
    if a is None or (a.ward, a.street, a.detail) != (f["ward"], f["street"], f["detail"]):
        customer.address = Address(ward=f["ward"], street=f["street"], detail=f["detail"])
    db.session.commit()
