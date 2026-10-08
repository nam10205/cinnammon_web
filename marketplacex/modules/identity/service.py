from __future__ import annotations

import secrets
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from ...errors import NotFound, ValidationError
from ...extensions import db
from ..admin import policy
from .models import Address, PasswordResetToken, User


def hash_password(pw: str) -> str:
    # pbkdf2: the system Python's hashlib lacks scrypt (werkzeug's default).
    return generate_password_hash(pw, method="pbkdf2:sha256")


def register(email: str, password: str, name: str) -> User:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValidationError("A valid email is required")
    if len(password or "") < 6:
        raise ValidationError("Password must be at least 6 characters")
    if not (name or "").strip():
        raise ValidationError("Name is required")
    if User.query.filter_by(email=email).first():
        raise ValidationError("Email already registered")
    u = User(email=email, name=name.strip(), role="customer", password_hash=hash_password(password),
             created_at=policy.now())
    db.session.add(u)
    db.session.commit()
    return u


def authenticate(email: str, password: str) -> User:
    u = User.query.filter_by(email=(email or "").strip().lower()).first()
    if not u or not check_password_hash(u.password_hash, password or ""):
        raise ValidationError("Invalid email or password")
    if u.status != "active":
        raise ValidationError("This account is suspended")
    return u


def get_user(user_id: int) -> User:
    u = db.session.get(User, user_id)
    if u is None:
        raise NotFound("User not found")
    return u


def add_address(user: User, recipient: str, phone: str, line: str, city: str, is_default: bool = False) -> Address:
    if not all(x and str(x).strip() for x in (recipient, phone, line, city)):
        raise ValidationError("All address fields are required")
    if is_default or not user.addresses:
        for a in user.addresses:
            a.is_default = False
        is_default = True
    a = Address(user_id=user.id, recipient=recipient, phone=phone, line=line, city=city, is_default=is_default)
    db.session.add(a)
    db.session.commit()
    return a


def default_address(user: User) -> Address | None:
    for a in user.addresses:
        if a.is_default:
            return a
    return user.addresses[0] if user.addresses else None


def start_recovery(email: str) -> str | None:
    u = User.query.filter_by(email=(email or "").strip().lower()).first()
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
