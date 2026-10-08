from helpers import delivered_order, seller_user
from marketplacex.modules.admin import policy
from marketplacex.modules.returns import service as returns
from marketplacex.modules.settlement import service as settlement
from marketplacex.modules.settlement.models import LedgerEntry


def test_delivery_posts_balanced_held_entries(alice):
    o = delivered_order(alice, "P03")
    assert settlement.is_balanced(o.id)
    entries = LedgerEntry.query.filter_by(order_id=o.id).all()
    assert {e.status for e in entries} == {"held"}
    payable = next(e for e in entries if e.account == "seller_payable")
    assert payable.credit_vnd == 899000 - 899000 * 5 // 100


def test_release_after_window(alice, make_user):
    o = delivered_order(alice, "P03")
    assert settlement.release_eligible(make_user("admin")) == 0
    policy.advance_clock(8 * 24)
    assert settlement.release_eligible(make_user("admin")) == 1
    assert o.status == "Completed"
    st = settlement.statement(o.shop)
    assert st["released_vnd"] > 0 and st["held_vnd"] == 0


def test_open_return_blocks_release(alice, make_user):
    o = delivered_order(alice, "P03")
    returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    policy.advance_clock(8 * 24)
    assert settlement.release_eligible(make_user("admin")) == 0


def test_refund_posts_reversal(alice):
    o = delivered_order(alice, "P03")
    c = returns.open_case(alice, o.id, {o.items[0].id: 1}, "r", "refund_only", "s")
    returns.seller_respond(seller_user("sportzone@demo"), c.id, "accept", "ok")
    assert settlement.is_balanced(o.id)
    assert settlement.statement(o.shop)["refunds_vnd"] == c.refund_amount_vnd


def test_statement_page(client, alice, login):
    delivered_order(alice, "P03")
    login(client, seller_user("sportzone@demo"))
    assert b"held" in client.get("/seller/settlement").data.lower()
