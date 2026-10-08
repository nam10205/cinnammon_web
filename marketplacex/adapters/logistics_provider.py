"""Fake carrier: quotes, labels and tracking events (report §7.6)."""
from __future__ import annotations

import uuid


class FakeLogisticsProvider:
    NEXT = ["picked_up", "in_transit", "out_for_delivery", "delivered"]
    FLAT_FEE_VND = 28000

    def quote(self, from_city: str, to_city: str) -> int:
        return self.FLAT_FEE_VND

    def create(self, order_id: int, kind: str) -> tuple[str, str]:
        tracking = ("RT" if kind == "return" else "MX") + uuid.uuid4().hex[:10].upper()
        return tracking, f"/seller/labels/{tracking}"


carrier = FakeLogisticsProvider()
