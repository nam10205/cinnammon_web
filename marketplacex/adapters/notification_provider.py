"""Fake email/SMS/push provider with a configurable failure rate (report §4.5 notification failure metric)."""
from __future__ import annotations

import random


class FakeNotificationProvider:
    def __init__(self, failure_rate: float = 0.0):
        self.failure_rate = failure_rate

    def send(self, channel: str, to: str, body: str) -> bool:
        if channel == "in_app":
            return True
        return random.random() >= self.failure_rate
