import pytest

from helpers import alice_user, cat, paid_order, pending_product, shop_id
from marketplacex.errors import ValidationError
from marketplacex.modules.admin import service as admin
from marketplacex.modules.audit.models import AuditEvent
from marketplacex.modules.identity import service as identity
from marketplacex.modules.reporting import service as reporting


def test_moderation_requires_reason(seeded, make_user):
    p = pending_product()
    with pytest.raises(ValidationError):
        admin.moderate_listing(make_user("admin"), p.id, True, "")
    admin.moderate_listing(make_user("admin"), p.id, False, "prohibited term")
    assert p.status == "rejected" and p.moderation_reason == "prohibited term"
    assert AuditEvent.query.filter_by(action="listing.rejected").count() == 1


def test_approve_listing_makes_it_searchable(seeded, make_user):
    from marketplacex.modules.search import service as search
    from marketplacex.modules.search.query import build_query
    p = pending_product()
    admin.moderate_listing(make_user("admin"), p.id, True, "ok after review")
    assert p.status == "active"
    assert any(i.product.id == p.id for i in search.search(build_query("text", "replica")).items)


def test_bulk_moderation_preview_and_job(seeded, make_user):
    p = pending_product()
    assert [x.id for x in admin.bulk_moderate_preview([p.id])] == [p.id]
    job = admin.bulk_moderate(make_user("admin"), [p.id, 99999], False, "policy sweep")
    assert job["done"] == 1 and job["failed"] == 1 and job["job_id"]


def test_suspended_user_cannot_login(seeded, make_user):
    admin.suspend_user(make_user("admin"), alice_user().id, True, "fraud")
    with pytest.raises(ValidationError):
        identity.authenticate("alice@demo", "demo123")


def test_taxonomy_and_campaign(seeded, make_user):
    a = make_user("admin")
    c = admin.save_category(a, {"name": "Sandals", "parent_id": cat("Fashion").id, "attribute_schema": "size, color",
                                "reason": "new category"})
    assert c.attribute_schema == ["size", "color"]
    with pytest.raises(ValidationError):
        admin.delete_category(a, cat("Shoes").id, "cleanup")
    camp = admin.save_campaign(a, {"name": "11.11", "budget_vnd": 5000000, "days": 10, "reason": "plan"})
    v = admin.save_voucher(a, {"campaign_id": camp.id, "code": "ELEVEN", "kind": "fixed", "value": 50000,
                               "min_spend_vnd": 0, "max_discount_vnd": "", "usage_limit": 100, "shop_id": "",
                               "reason": "launch"})
    assert v.campaign_id == camp.id


def test_verify_shop(seeded, make_user):
    from helpers import seller_user
    from marketplacex.modules.seller import service as seller_svc
    sh = seller_svc.create_shop(seller_user("techhub@demo"), "TechHub 2", "Hue")
    seller_svc.submit_verification(seller_user("techhub@demo"), sh.id, "licence")
    admin.verify_shop(make_user("admin"), sh.id, True, "documents ok")
    assert sh.verification_status == "verified"


def test_policy_and_clock(seeded, make_user):
    from marketplacex.modules.admin import policy
    admin.set_policy(make_user("admin"), "return_window_days", "10", "holiday season")
    assert policy.get_int("return_window_days") == 10


def test_reports_shape(alice):
    paid_order(alice, "P03", 1)
    r = reporting.orders_by_status()
    assert r.get("Confirmed", 0) >= 1 and reporting.payment_mismatches() == []
    assert 0 <= reporting.zero_result_rate() <= 1 and 0 <= reporting.notification_failure_rate() <= 1


def test_admin_pages_render(client, seeded, login, make_user):
    login(client, make_user("admin"))
    for u in ["/admin/", "/admin/categories", "/admin/campaigns", "/admin/policy", "/admin/moderation", "/admin/users",
              "/admin/audit"]:
        assert client.get(u).status_code == 200, u


def test_admin_pages_forbidden_for_seller(client, seeded, login):
    from helpers import seller_user
    login(client, seller_user("sportzone@demo"))
    assert client.get("/admin/moderation").status_code == 403
