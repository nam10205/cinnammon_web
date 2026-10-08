"""Demo seed data. Uses services so invariants hold."""
from __future__ import annotations

from .modules.admin.policy import ensure_defaults


def run() -> None:
    ensure_defaults()
