"""Single source of time (naive UTC) so tests can monkeypatch ``marketplacex.clock.now``."""
from __future__ import annotations

from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
