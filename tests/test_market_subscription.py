"""The dataset subscription: pages, the activate-once rule, the key that
opens the full view and dies with the subscription, and the webhook's
signature check.

The DB tests write rows tagged ``cs_test_pytest_sub`` and delete them
again; they commit, because the code under test commits, so the cleanup
is in a ``finally``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services import market_subscription as msub

MARKET = {"id": 2, "name": "AI in the SOC", "is_public": True}
CONFIG = {"STRIPE_SECRET_KEY": "sk_test_x",
          "STRIPE_SUB_WEBHOOK_SECRET": "whsec_test_x",
          "STRIPE_PRICE_SUB_DATASET": "price_dataset",
          "STRIPE_PRICE_SUB_MCP": "price_mcp"}


@pytest.fixture()
def configured(monkeypatch):
    for k, v in CONFIG.items():
        monkeypatch.setenv(k, v)


@pytest.fixture()
def conn():
    from app.database import get_database_instance

    try:
        c = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database available: {exc}")
    if c.execute(text("SELECT to_regclass('market_subscriptions')")).scalar() is None:
        pytest.skip("market_subscriptions not migrated here")
    try:
        yield c
    finally:
        c.rollback()
        c.execute(text("DELETE FROM market_subscriptions"
                       " WHERE stripe_session_id LIKE 'cs_test_pytest_sub%'"
                       " OR ip = 'pytest-ip'"))
        c.commit()
        c.close()


def _session(sid="cs_test_pytest_sub_1", paid=True, app=msub.META_APP, plan="dataset"):
    return {"id": sid, "payment_status": "paid" if paid else "unpaid",
            "customer": "cus_test_1", "subscription": "sub_test_pytest_1",
            "metadata": {"app": app, "market_id": "2", "plan": plan},
            "customer_details": {"email": "Buyer@Example.com", "name": "Buyer Person"}}


def _insert(c, sid, plan="dataset", ip=None, email="buyer@example.com"):
    return c.execute(text("""
        INSERT INTO market_subscriptions (market_id, plan, amount_cents, email, ip,
                                          site, stripe_session_id)
        VALUES (2, :p, 17900, :e, :ip, 'https://aisocnews.com', :s) RETURNING id
    """), {"p": plan, "e": email, "ip": ip, "s": sid}).scalar()


def test_is_configured_needs_everything(monkeypatch, configured):
    assert msub.is_configured()
    monkeypatch.delenv("STRIPE_SUB_WEBHOOK_SECRET")
    assert not msub.is_configured()


def test_form_page_states_the_one_plan_and_posts_to_checkout(configured):
    """One plan is not a choice: the page states it with its price and
    carries it in a hidden field rather than a radio with nothing to switch to."""
    page = msub.build_subscribe_page(
        MARKET, front_href="/", about_href="/?page=about",
        action="/api/market-monitor/markets/2/subscribe/checkout")
    assert "$139/mo" in page
    assert '<input type="hidden" name="plan" value="mcp">' in page
    assert 'type="radio"' not in page
    assert 'action="/api/market-monitor/markets/2/subscribe/checkout"' in page
    assert 'name="website"' in page          # the honeypot
    assert "MCP" in page


def test_form_page_says_what_the_key_adds(configured):
    """The pages are free to read; the key is how a subscriber's tools reach
    the data under them. With the vendor count known the list says how many."""
    page = msub.build_subscribe_page(
        MARKET, front_href="/", about_href="/?page=about",
        action="/api/market-monitor/markets/2/subscribe/checkout",
        totals={"total": 94, "named": 10})
    assert "What the key adds" in page
    assert "each of the 94 vendors" in page
    assert "headcount, hiring, funding" in page and "funding rounds" in page
    bare = msub.build_subscribe_page(
        MARKET, front_href="/", about_href="/?page=about",
        action="/api/market-monitor/markets/2/subscribe/checkout")
    assert "What the key adds" in bare and "each vendor compares" in bare
    assert "94 vendors" not in bare


def test_help_page_carries_the_endpoint_and_the_clients(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://bugfixing.aunoo.ai")
    page = msub.build_help_page(MARKET, front_href="/", about_href="/?page=about")
    assert "https://bugfixing.aunoo.ai/mcp" in page
    assert "Authorization: Bearer YOUR_KEY" in page
    for client in ("Claude Code", "Claude Desktop", "Cursor", "VS Code"):
        assert client in page


def test_access_href_uses_the_public_host_when_there_is_one(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://bugfixing.aunoo.ai")
    assert (msub.access_href("https://aisocnews.com", 2, "dsk_x")
            == "https://aisocnews.com/?key=dsk_x")
    assert msub.access_href("https://bugfixing.aunoo.ai", 2, "dsk_x") == (
        "https://bugfixing.aunoo.ai/api/market-monitor/markets/2/report.html?view=v2&key=dsk_x")


def test_activate_flips_once_and_only_the_winner_gets_the_key(conn):
    _insert(conn, "cs_test_pytest_sub_1")
    row, access, mcp = msub.activate(conn, _session())
    assert row["status"] == "active" and access and access.startswith("dsk_")
    assert mcp is None                       # dataset plan mints no MCP key
    again, access2, _ = msub.activate(conn, _session())
    assert again["status"] == "active" and access2 is None


def test_activate_ignores_foreign_and_unpaid_sessions(conn):
    _insert(conn, "cs_test_pytest_sub_2")
    assert msub.activate(conn, _session("cs_test_pytest_sub_2", app="saas"))[0] is None
    row, access, _ = msub.activate(conn, _session("cs_test_pytest_sub_2", paid=False))
    assert row is None and access is None


def test_the_key_opens_only_an_active_subscription(conn):
    _insert(conn, "cs_test_pytest_sub_3")
    _, access, _ = msub.activate(conn, _session("cs_test_pytest_sub_3"))
    assert msub.active_by_key(conn, 2, access)["plan"] == "dataset"
    assert msub.active_by_key(conn, 3, access) is None      # wrong market
    assert msub.active_by_key(conn, 2, "dsk_wrong") is None
    moved = msub.apply_lifecycle(conn, {"id": "sub_test_pytest_1",
                                        "metadata": {"app": msub.META_APP},
                                        "status": "canceled"}, deleted=True)
    assert moved == "cancelled"
    assert msub.active_by_key(conn, 2, access) is None


def test_past_due_keeps_access_through_the_retry_window(conn):
    _insert(conn, "cs_test_pytest_sub_4")
    _, access, _ = msub.activate(conn, _session("cs_test_pytest_sub_4"))
    sub = {"id": "sub_test_pytest_1", "metadata": {"app": msub.META_APP},
           "status": "past_due"}
    assert msub.apply_lifecycle(conn, sub, deleted=False) == "past_due"
    assert msub.active_by_key(conn, 2, access) is not None
    sub["status"] = "active"
    assert msub.apply_lifecycle(conn, sub, deleted=False) == "active"


def test_reissue_rotates_the_key_and_kills_the_old_one(conn):
    _insert(conn, "cs_test_pytest_sub_5")
    _, old, _ = msub.activate(conn, _session("cs_test_pytest_sub_5"))
    row, new, mcp = msub.reissue(conn, _session("cs_test_pytest_sub_5"))
    assert new and new != old and mcp is None
    flag = conn.execute(text("SELECT notified_buyer FROM market_subscriptions WHERE id = :i"),
                        {"i": row["id"]}).scalar()
    assert flag is False                      # reset, so notify mails the fresh one
    assert msub.active_by_key(conn, 2, new) is not None
    assert msub.active_by_key(conn, 2, old) is None


def test_reissue_refuses_cancelled_and_foreign(conn):
    _insert(conn, "cs_test_pytest_sub_6")
    msub.activate(conn, _session("cs_test_pytest_sub_6"))
    assert msub.reissue(conn, _session("cs_test_pytest_sub_6", app="saas"))[1] is None
    msub.apply_lifecycle(conn, {"id": "sub_test_pytest_1",
                                "metadata": {"app": msub.META_APP},
                                "status": "canceled"}, deleted=True)
    row, token, _ = msub.reissue(conn, _session("cs_test_pytest_sub_6"))
    assert token is None and row["status"] == "cancelled"


def test_lifecycle_ignores_foreign_subscriptions(conn):
    assert msub.apply_lifecycle(conn, {"id": "sub_someone_elses",
                                       "metadata": {"app": "saas"},
                                       "status": "canceled"}, deleted=True) is None


def test_per_address_limit_counts_only_subscriptions(conn):
    for i in range(msub.CHECKOUTS_PER_IP_PER_DAY):
        _insert(conn, f"cs_test_pytest_sub_ip{i}", ip="pytest-ip")
    conn.commit()
    assert msub.too_many_today(conn, "pytest-ip")
    assert not msub.too_many_today(conn, "10.0.0.99")


def test_webhook_rejects_a_bad_signature(configured):
    with pytest.raises(Exception):
        msub.event_from_webhook(b"{}", "t=1,v1=bad")
