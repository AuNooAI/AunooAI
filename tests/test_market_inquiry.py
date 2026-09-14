"""The paid analyst call: pages, the paid-once rule, the mail-once rule,
the per-address limit and the webhook's signature check.

The DB tests write rows tagged ``cs_test_pytest`` and delete them again;
they commit, because the code under test commits, so the cleanup is in a
``finally``.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.services import market_inquiry as inq

MARKET = {"id": 2, "name": "AI in the SOC", "is_public": True}
CONFIG = {"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_PRICE_INQUIRY_30": "price_30",
          "STRIPE_PRICE_INQUIRY_60": "price_60",
          "MARKET_INQUIRY_BOOKING_URL_30": "https://calendar.app.google/thirty",
          "MARKET_INQUIRY_BOOKING_URL_60": "https://calendar.app.google/sixty"}


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
    if c.execute(text("SELECT to_regclass('market_inquiries')")).scalar() is None:
        pytest.skip("market_inquiries not migrated here")
    try:
        yield c
    finally:
        c.rollback()
        c.execute(text("DELETE FROM market_inquiries WHERE stripe_session_id LIKE 'cs_test_pytest%'"
                       " OR ip = 'pytest-ip'"))
        c.commit()
        c.close()


def _session(sid="cs_test_pytest_1", paid=True, app=inq.META_APP):
    return {"id": sid, "payment_status": "paid" if paid else "unpaid",
            "payment_intent": "pi_test_1",
            "metadata": {"app": app, "market_id": "2"},
            "customer_details": {"email": "Buyer@Example.com", "name": "Buyer Person"}}


def _insert(c, sid, ip=None, email="buyer@example.com"):
    return c.execute(text("""
        INSERT INTO market_inquiries (market_id, length_minutes, amount_cents, email, ip,
                                      stripe_session_id)
        VALUES (2, 30, 25000, :e, :ip, :s) RETURNING id
    """), {"e": email, "ip": ip, "s": sid}).scalar()


def test_is_configured_needs_everything(monkeypatch, configured):
    assert inq.is_configured()
    monkeypatch.delenv("MARKET_INQUIRY_BOOKING_URL_60")
    assert not inq.is_configured()


def test_form_page_shows_both_prices_and_posts_to_checkout(configured):
    page = inq.build_inquiry_page(MARKET, front_href="/", about_href="/?page=about",
                                  action="/api/market-monitor/markets/2/inquiry/checkout")
    assert "$250" in page and "$450" in page
    assert 'action="/api/market-monitor/markets/2/inquiry/checkout"' in page
    assert 'name="website"' in page          # the honeypot
    assert "Schedule an inquiry" in page


def test_form_page_keeps_values_and_shows_the_error(configured):
    page = inq.build_inquiry_page(MARKET, front_href="/", about_href="/", action="/x",
                                  error="That email address does not look right.",
                                  values={"minutes": 60, "name": "Ada", "email": "nope",
                                          "subject": "Torq vs Tines"})
    assert 'value="60" checked' in page and 'value="Ada"' in page and "Torq vs Tines" in page
    assert 'role="alert"' in page


def test_done_page_hands_over_the_booking_link_for_the_length_bought(configured):
    row = {"length_minutes": 60, "amount_cents": 45000, "currency": "usd",
           "email": "buyer@example.com"}
    page = inq.build_done_page(MARKET, row, paid=True, front_href="/", about_href="/")
    assert "https://calendar.app.google/sixty" in page and "$450" in page
    pending = inq.build_done_page(MARKET, row, paid=False, front_href="/", about_href="/")
    assert "calendar.app.google" not in pending and "pending" in pending.lower()


def test_mark_paid_flips_once_and_ignores_foreign_sessions(conn):
    _insert(conn, "cs_test_pytest_1")
    first = inq.mark_paid(conn, _session())
    assert first and first["status"] == "paid" and first["email"] == "buyer@example.com"
    assert first["name"] == "Buyer Person"
    again = inq.mark_paid(conn, _session())
    assert again and again["status"] == "paid" and again["paid_at"] == first["paid_at"]
    assert inq.mark_paid(conn, _session(app="something-else")) is None
    assert inq.mark_paid(conn, _session(paid=False)) is None
    assert inq.mark_paid(conn, _session(sid="cs_test_pytest_unknown")) is None


def test_notify_sends_each_mail_once(conn, configured, monkeypatch):
    from app.services import email_service

    sent = []

    class _Svc:
        def is_available(self):
            return True

        def send_email(self, to, subject, html, text=None, **kw):
            sent.append((tuple(to), subject, kw.get("extra_headers")))
            return True

    monkeypatch.setattr(email_service, "EmailService", _Svc)
    monkeypatch.setenv("MARKET_TRIAL_NOTIFY_EMAIL", "editor@example.com")
    _insert(conn, "cs_test_pytest_2")
    row = inq.mark_paid(conn, _session(sid="cs_test_pytest_2"))
    inq.notify(conn, row, MARKET)
    inq.notify(conn, row, MARKET)
    assert len(sent) == 2
    assert sent[0][0] == ("editor@example.com",) and "Paid inquiry" in sent[0][1]
    assert sent[1][0] == ("buyer@example.com",) and sent[1][2] == {"Reply-To": "editor@example.com"}
    flags = conn.execute(text("SELECT notified_editors, notified_buyer FROM market_inquiries"
                              " WHERE stripe_session_id = 'cs_test_pytest_2'")).fetchone()
    assert flags == (True, True)


def test_per_address_limit_counts_only_inquiries(conn):
    for i in range(inq.INQUIRIES_PER_IP_PER_DAY):
        _insert(conn, f"cs_test_pytest_ip{i}", ip="pytest-ip")
    conn.commit()
    assert inq.too_many_today(conn, "pytest-ip")
    assert not inq.too_many_today(conn, "pytest-other")
    assert not inq.too_many_today(conn, None)


def test_webhook_rejects_a_bad_signature(configured, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes.market_inquiry_routes import router

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    app = FastAPI()
    app.include_router(router, prefix="/api/market-monitor")
    client = TestClient(app)
    r = client.post("/api/market-monitor/markets/2/inquiry/webhook", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=bad"})
    assert r.status_code == 400
