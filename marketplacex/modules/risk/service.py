"""Risk evaluation hooks. Rules arrive in Task 18; until then every checkout is approved."""
from __future__ import annotations


def evaluate_checkout(customer, group) -> str:
    return "approved"
