"""Append-only audit trail (report §8.5)."""
from __future__ import annotations

import hashlib
import json

from ...events import correlation_id
from ...extensions import db
from ..admin import policy
from .models import AuditEvent


def _digest(x) -> str | None:
    if x is None:
        return None
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()[:16]


def record(actor, action: str, target_type: str, target_id, reason: str | None = None,
           before: dict | None = None, after: dict | None = None) -> AuditEvent:
    ev = AuditEvent(actor_id=getattr(actor, "id", None), role=getattr(actor, "role", "system"),
                    action=action, target_type=target_type, target_id=str(target_id), reason=reason,
                    before_digest=_digest(before), after_digest=_digest(after),
                    correlation_id=correlation_id(), at=policy.now())
    db.session.add(ev)
    db.session.flush()
    return ev


def latest(limit: int = 200) -> list[AuditEvent]:
    return AuditEvent.query.order_by(AuditEvent.id.desc()).limit(limit).all()
