"""Fake payment provider behind a canonical adapter interface (report §7.6). No card data ever enters the platform."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid


class FakePaymentProvider:
    def __init__(self, secret: str):
        self.secret = secret.encode()

    def authorize(self, amount_vnd: int, attempt_id: str) -> str:
        return "PAY-" + uuid.uuid4().hex[:8].upper()

    def void(self, provider_ref: str) -> None:
        return None

    def refund(self, provider_ref: str, amount_vnd: int, key: str) -> str:
        return "RFD-" + uuid.uuid4().hex[:8].upper()

    def sign(self, payload: dict) -> str:
        return hmac.new(self.secret, json.dumps(payload, sort_keys=True).encode(), hashlib.sha256).hexdigest()

    def verify(self, payload: dict, signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), signature or "")
