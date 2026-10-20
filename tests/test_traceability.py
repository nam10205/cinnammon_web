"""README must trace every Figure 1 use case, FR and BR to code and a real test (report §15.3)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USE_CASES = [
    "Manage Account", "Discover Product", "Search by Text", "Search by Voice", "Search by Image", "Manage Cart",
    "Checkout", "Validate Cart", "Apply Promotion", "Reserve Stock", "Authorize Payment", "Create Order",
    "Deliver Notification", "Track Order", "Review Purchase", "Request Return or Refund", "Escalate Dispute",
    "Chat with Seller", "Manage Shop", "Manage Listing", "Manage Inventory and Price", "Fulfil Order",
    "Create and Track Shipment", "Handle Return", "View Settlement", "Chat with Customer", "Manage Taxonomy",
    "Manage Campaign", "Configure Platform Policy", "Govern Users and Content", "View Operational Report",
    "Manage Customer Case", "Assist Dispute", "Process Payment",
]


def _readme():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        return f.read()


def test_every_use_case_fr_and_br_traced():
    text = _readme()
    rows = [l for l in text.splitlines() if l.startswith("|")]
    for uc in USE_CASES:
        assert any(f"| {uc} |" in r for r in rows), uc
    for i in range(1, 31):
        assert any(f"| FR{i:02d} |" in r for r in rows), f"FR{i:02d}"
    for i in range(1, 9):
        assert any(f"| BR{i:02d} |" in r for r in rows), f"BR{i:02d}"


def test_referenced_tests_exist():
    refs = re.findall(r"(tests/test_\w+\.py)::(\w+)", _readme())
    assert len(refs) >= 40
    for path, name in refs:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            assert re.search(rf"def {name}\b", f.read()), f"{path}::{name}"
