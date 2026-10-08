"""In-process event bus standing in for the report's event broker (§7.3, §7.5)."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Callable

from flask import g, has_request_context

from .extensions import db


class EventLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_uid = db.Column(db.String(32), unique=True, default=lambda: uuid.uuid4().hex)
    name = db.Column(db.String(64), index=True, nullable=False)
    aggregate_id = db.Column(db.String(64), index=True)
    payload = db.Column(db.JSON, default=dict)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow)
    correlation_id = db.Column(db.String(32))


class ProcessedEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consumer = db.Column(db.String(64), nullable=False)
    event_id = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint("consumer", "event_id"),)


_subscribers: dict[str, dict[str, Callable]] = defaultdict(dict)


def correlation_id() -> str:
    if has_request_context() and getattr(g, "correlation_id", None):
        return g.correlation_id
    return "cli"


def subscribe(name: str, consumer: str):
    def deco(fn):
        _subscribers[name][consumer] = fn
        return fn
    return deco


def _deliver(event: EventLog) -> None:
    for consumer, fn in list(_subscribers.get(event.name, {}).items()):
        done = ProcessedEvent.query.filter_by(consumer=consumer, event_id=event.id).first()
        if done:
            continue
        db.session.add(ProcessedEvent(consumer=consumer, event_id=event.id))
        db.session.flush()
        fn(event)


def publish(name: str, aggregate_id, payload: dict) -> EventLog:
    from .modules.admin import policy
    ev = EventLog(name=name, aggregate_id=str(aggregate_id), payload=payload,
                  occurred_at=policy.now(), correlation_id=correlation_id())
    db.session.add(ev)
    db.session.flush()
    _deliver(ev)
    return ev


def redeliver(event: EventLog) -> None:
    _deliver(event)
