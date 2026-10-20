from __future__ import annotations

import secrets
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from ...errors import NotFound, ValidationError
from ...extensions import db
from ..admin import policy
from .models import ROLES, Account, Address, Customer, FullName, PasswordResetToken


def hash_password(pw: str) -> str:
    # pbkdf2: the system Python's hashlib lacks scrypt (werkzeug's default).
    from flask import current_app
    method = "pbkdf2:sha256:1000" if current_app.testing else "pbkdf2:sha256"
    return generate_password_hash(pw, method=method)


def split_name(name: str) -> tuple[str, str, str]:
    """First token, middle tokens joined by spaces, last token. One word -> (word, "", "")."""
    parts = (name or "").split()
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def create_account(email: str, name: str, role: str, password: str, phone: str | None = None,
                   created_at=None) -> Account:
    """Create a login; a customer also gets its ERD FullName + Customer rows."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValidationError("A valid email is required")
    if len(password or "") < 6:
        raise ValidationError("Password must be at least 6 characters")
    if not (name or "").strip():
        raise ValidationError("Name is required")
    if role not in ROLES:
        raise ValidationError("Unknown role")
    if Account.query.filter_by(email=email).first():
        raise ValidationError("Email already registered")
    a = Account(email=email, name=" ".join(name.split()), role=role, phone=phone,
                password_hash=hash_password(password), created_at=created_at or policy.now())
    db.session.add(a)
    if role == "customer":
        first, middle, last = split_name(name)
        fn = FullName(first_name=first, middle_name=middle, last_name=last)
        a.name = fn.display
        db.session.add(Customer(full_name=fn, account=a, email=email, phone_number=phone))
    db.session.commit()
    return a


def register(email: str, password: str, name: str) -> Account:
    return create_account(email, name, "customer", password)


def authenticate(email: str, password: str) -> Account:
    u = Account.query.filter_by(email=(email or "").strip().lower()).first()
    if not u or not check_password_hash(u.password_hash, password or ""):
        raise ValidationError("Invalid email or password")
    if u.status != "active":
        raise ValidationError("This account is suspended")
    return u


def get_user(user_id: int) -> Account:
    u = db.session.get(Account, user_id)
    if u is None:
        raise NotFound("User not found")
    return u


def add_address(account: Account, recipient: str, phone: str, street: str, ward: str, district: str, city: str,
                detail: str = "", is_default: bool = False) -> Address:
    c = account.customer
    if c is None:
        raise ValidationError("Only customers have addresses")
    if not all(x and str(x).strip() for x in (recipient, phone, street, ward, city)):
        raise ValidationError("Recipient, phone, street, ward and city are required")
    if is_default or not c.addresses:
        for a in c.addresses:
            a.is_default = False
        is_default = True
    a = Address(customer=c, recipient=recipient, phone=phone, street=street, ward=ward, district=district or None,
                city=city, detail=detail or None, is_default=is_default)
    db.session.add(a)
    if is_default:
        c.default_address = a
    db.session.commit()
    return a


def default_address(user: Account) -> Address | None:
    for a in user.addresses:
        if a.is_default:
            return a
    return user.addresses[0] if user.addresses else None


def start_recovery(email: str) -> str | None:
    u = Account.query.filter_by(email=(email or "").strip().lower()).first()
    if not u:
        return None
    tok = secrets.token_urlsafe(24)
    db.session.add(PasswordResetToken(token=tok, user_id=u.id, expires_at=policy.now() + timedelta(hours=1)))
    db.session.commit()
    return tok


def reset_password(token: str, new_password: str) -> None:
    t = db.session.get(PasswordResetToken, token)
    if not t or t.used or t.expires_at < policy.now():
        raise ValidationError("Reset link is invalid or expired")
    if len(new_password or "") < 6:
        raise ValidationError("Password must be at least 6 characters")
    u = get_user(t.user_id)
    u.password_hash = hash_password(new_password)
    t.used = True
    db.session.commit()
