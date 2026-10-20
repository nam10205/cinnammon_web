"""Platform policy values and the demo clock. Always use via `policy.now()` / `policy.get_int()`."""
from __future__ import annotations

from datetime import datetime, timedelta

from ...extensions import db
from .models import Clock, PlatformPolicy

DEFAULTS = {
    "return_window_days": "7",
    "platform_fee_pct": "5",
    "seller_response_hours": "48",
    "reservation_ttl_min": "15",
    "quote_ttl_min": "10",
    "prohibited_terms": "counterfeit,replica,fake",
}


def ensure_defaults() -> None:
    for k, v in DEFAULTS.items():
        if db.session.get(PlatformPolicy, k) is None:
            db.session.add(PlatformPolicy(key=k, value=v))
    if db.session.get(Clock, 1) is None:
        db.session.add(Clock(id=1, offset_hours=0))
    db.session.commit()


def _clock() -> Clock:
    c = db.session.get(Clock, 1)
    if c is None:
        c = Clock(id=1, offset_hours=0)
        db.session.add(c)
        db.session.flush()
    return c


def now() -> datetime:
    return datetime.utcnow() + timedelta(hours=_clock().offset_hours)


def advance_clock(hours: int) -> None:
    _clock().offset_hours += int(hours)
    db.session.commit()


def reset_clock() -> None:
    _clock().offset_hours = 0
    db.session.commit()


def clock_offset_hours() -> int:
    return _clock().offset_hours


def get_str(key: str) -> str:
    row = db.session.get(PlatformPolicy, key)
    return row.value if row else DEFAULTS[key]


def get_int(key: str) -> int:
    return int(get_str(key))


def set_value(key: str, value, actor) -> None:
    from ..audit import service as audit
    row = db.session.get(PlatformPolicy, key)
    before = {key: row.value if row else None}
    if row is None:
        row = PlatformPolicy(key=key, value=str(value))
        db.session.add(row)
    else:
        row.value = str(value)
    audit.record(actor, "policy.set", "policy", key, reason=f"set {key}", before=before, after={key: str(value)})
    db.session.commit()


def all_values() -> dict:
    return {p.key: p.value for p in PlatformPolicy.query.order_by(PlatformPolicy.key)}
