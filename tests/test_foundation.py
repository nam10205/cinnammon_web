import pytest

def test_register_and_login(client):
    r = client.post("/register", data={"email": "b@x", "password": "pw12345", "name": "B"}, follow_redirects=True)
    assert r.status_code == 200
    client.get("/logout")
    r = client.post("/login", data={"email": "b@x", "password": "pw12345"}, follow_redirects=True)
    assert b"B" in r.data


def test_require_role_blocks_wrong_role(client, make_user, login):
    login(client, make_user("customer"))
    assert client.get("/admin/").status_code == 403


def test_event_consumer_runs_once_on_redelivery(app):
    from marketplacex import events
    seen = []

    @events.subscribe("TestHappened", "test-consumer")
    def h(ev):
        seen.append(ev.id)
    ev = events.publish("TestHappened", 1, {})
    events.redeliver(ev)
    assert seen == [ev.id]


def test_clock_advance(app):
    from marketplacex.modules.admin import policy
    t0 = policy.now()
    policy.advance_clock(48)
    assert (policy.now() - t0).total_seconds() >= 48 * 3600 - 5


def test_audit_record_has_digest(app, make_user):
    from marketplacex.modules.audit import service as audit
    a = audit.record(make_user("admin"), "x.do", "thing", 1, reason="r", before={"a": 1}, after={"a": 2})
    assert a.before_digest != a.after_digest and a.reason == "r"


def test_password_recovery(app, make_user):
    from marketplacex.modules.identity import service as ids
    u = make_user("customer", email="r@x")
    tok = ids.start_recovery("r@x")
    ids.reset_password(tok, "newpass1")
    assert ids.authenticate("r@x", "newpass1").id == u.id


def test_demo_login_buttons(client, make_user):
    make_user("admin", email="admin@demo")
    r = client.post("/demo-login/admin", follow_redirects=True)
    assert r.status_code == 200


def test_only_three_roles():
    from marketplacex.modules.identity.models import ROLES
    assert ROLES == ("customer", "seller", "admin")


def test_no_risk_policies(app):
    from marketplacex.modules.admin import policy
    assert not [k for k in policy.DEFAULTS if k.startswith("risk_")]
