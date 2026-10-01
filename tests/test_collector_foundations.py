"""The shared collector contract, URL identity, date parser and quota ledger.

These four modules are byte-identical in the monolith and the SaaS tree; the
tests run unchanged in both. Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md,
work packages 1, 4, 7, 20, 21, 28 and 30.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.collectors import contracts as c
from app.collectors import dates as d
from app.collectors import url_identity as u
from app.services import shared_ledger as sl


# ---------------------------------------------------------------------------
# CollectionResult
# ---------------------------------------------------------------------------

def test_empty_success_advances_but_failure_does_not():
    ok = c.CollectionResult.ok([])
    assert ok.may_advance_checkpoint
    failed = c.CollectionResult.failure(c.ERR_HTTP_5XX, "x", retryable=True)
    assert not failed.may_advance_checkpoint
    assert failed.items == []


def test_partial_keeps_items_and_continuation():
    res = c.CollectionResult.partial([{"url": "a"}], truncated_reason=c.TRUNC_TIME_BUDGET,
                                     continuation={"page": 2})
    assert res.status == c.STATUS_PARTIAL
    assert not res.may_advance_checkpoint
    assert res.continuation == {"page": 2}
    assert res.retryable


def test_parse_partial_blocks_checkpoint():
    res = c.CollectionResult.ok([{"url": "a"}])
    res.parse_partial = True
    assert not res.may_advance_checkpoint


def test_failure_message_is_never_empty():
    res = c.CollectionResult.failure(c.ERR_TIMEOUT, "", retryable=True)
    assert res.error_message == c.ERR_TIMEOUT


def test_merge_of_failed_route_makes_partial():
    a = c.CollectionResult.ok([{"url": "1"}], scope="subreddit")
    b = c.CollectionResult.failure(c.ERR_HTTP_4XX, "HTTP 429", retryable=True, scope="search")
    a.merge(b)
    assert a.status == c.STATUS_PARTIAL
    assert not a.coverage_complete
    assert a.error_code == c.ERR_HTTP_4XX
    assert a.diagnostics["routes"][0]["scope"] == "search"


def test_to_record_has_counts_and_no_items():
    res = c.CollectionResult.ok([{"url": "1"}]).mark_started().mark_finished()
    res.counts.add(received=3, filtered=2)
    rec = res.to_record()
    assert rec["counts"]["received"] == 3
    assert rec["item_count"] == 1
    assert "items" not in rec
    assert rec["duration_ms"] is not None


# ---------------------------------------------------------------------------
# Error classification (work package 28)
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status):
        self.status_code = status


class _HttpErr(Exception):
    def __init__(self, status, text=""):
        super().__init__(text)
        self.response = _Resp(status)


class ReadTimeout(Exception):
    """Mimics httpx.ReadTimeout, whose str() is empty."""


def test_httpx_style_timeout_names_class_and_host():
    code, msg, retryable = c.classify_exception(ReadTimeout(""), host="feeds.example.com")
    assert code == c.ERR_TIMEOUT
    assert "ReadTimeout" in msg and "feeds.example.com" in msg
    assert retryable
    assert msg.strip()


def test_http_statuses_map_to_codes():
    assert c.classify_exception(_HttpErr(429))[0] == c.ERR_QUOTA
    assert c.classify_exception(_HttpErr(406))[0] == c.ERR_HTTP_4XX
    assert c.classify_exception(_HttpErr(406))[2] is True  # transient
    assert c.classify_exception(_HttpErr(404))[2] is False
    assert c.classify_exception(_HttpErr(503))[0] == c.ERR_HTTP_5XX
    assert c.classify_exception(_HttpErr(403))[0] == c.ERR_AUTH


def test_quota_phrases_in_body_count_as_quota():
    code, _, retryable = c.classify_exception(ValueError("You have exceeded your assigned API credits"))
    assert code == c.ERR_QUOTA and retryable


def test_cancelled_is_classified_not_swallowed():
    code, _, _ = c.classify_exception(asyncio.CancelledError())
    assert code == c.ERR_CANCELLED


def test_dns_failure():
    import socket
    code, _, _ = c.classify_exception(socket.gaierror(-2, "Name or service not known"))
    assert code == c.ERR_DNS


# ---------------------------------------------------------------------------
# URL identity (work packages 4 and 30)
# ---------------------------------------------------------------------------

def test_seekingalpha_variants_collapse():
    a = "https://seekingalpha.com/news/1234-foo?feed_item_type=news"
    b = "https://seekingalpha.com/news/1234-foo"
    assert u.canonical_url(a) == u.canonical_url(b) == b


def test_bbc_variants_collapse_including_subdomain():
    a = "https://www.bbc.co.uk/news/articles/c1?at_medium=RSS&at_campaign=rss"
    b = "https://www.bbc.co.uk/news/articles/c1"
    assert u.canonical_url(a) == u.canonical_url(b)
    assert u.canonical_url("https://feeds.bbc.co.uk/x?at_medium=RSS") == "https://feeds.bbc.co.uk/x"


def test_functional_parameter_is_kept():
    a = "https://www.streamingmedia.com/Articles/News/Online-Video-News/x.aspx?ArticleID=1"
    b = "https://www.streamingmedia.com/Articles/News/Online-Video-News/x.aspx?ArticleID=2"
    assert u.canonical_url(a) != u.canonical_url(b)
    assert "ArticleID=1" in u.canonical_url(a)


def test_global_utm_and_fbclid_stripped_case_preserved_in_path():
    n = u.normalize_url("HTTPS://Example.com:443/Path/To?utm_source=x&fbclid=y&id=7#frag")
    assert n.canonical == "https://example.com/Path/To?id=7"
    assert sorted(n.stripped) == ["fbclid", "utm_source"]
    assert n.registry_version == u.registry_version()


def test_http_and_https_are_not_forced_equal():
    assert u.canonical_url("http://example.com/a") != u.canonical_url("https://example.com/a")


def test_trailing_slash_and_non_default_port_kept():
    assert u.canonical_url("https://example.com/a/") == "https://example.com/a/"
    assert u.canonical_url("https://example.com:8443/a") == "https://example.com:8443/a"


def test_invalid_url_is_not_an_identity():
    n = u.normalize_url("mailto:someone@example.com")
    assert not n.valid


def test_registry_file_overrides_and_versions(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    path.write_text('{"version": "test-2", "hosts": {"example.org": ["sess"]}}')
    monkeypatch.setenv("URL_TRACKING_REGISTRY_PATH", str(path))
    u._registry_cache = None
    try:
        assert u.registry_version() == "test-2"
        assert u.canonical_url("https://example.org/a?sess=1&id=2") == "https://example.org/a?id=2"
        # Built-ins still apply.
        assert u.canonical_url("https://example.org/a?utm_x=1") == "https://example.org/a"
    finally:
        monkeypatch.delenv("URL_TRACKING_REGISTRY_PATH")
        u._registry_cache = None


def test_social_identity_is_platform_and_post_id_not_url():
    a = u.choose_identity(record_type=u.RT_SOCIAL, platform="instagram", post_id="1",
                          url="https://www.instagram.com/brand/")
    b = u.choose_identity(record_type=u.RT_SOCIAL, platform="instagram", post_id="2",
                          url="https://www.instagram.com/brand/")
    assert a != b and a.method == u.ID_SOCIAL


def test_doi_identity_normalizes():
    a = u.choose_identity(record_type=u.RT_SCHOLARLY, doi="https://doi.org/10.1000/ABC.123")
    b = u.choose_identity(record_type=u.RT_SCHOLARLY, external_id="10.1000/abc.123")
    assert a == b and a.method == u.ID_DOI


def test_calendar_occurrence_key_beats_url():
    a = u.choose_identity(record_type=u.RT_CALENDAR, feed_scope="feed:1", occurrence_key="uid@2026-01-01",
                          url="https://cal.example.com/event")
    b = u.choose_identity(record_type=u.RT_CALENDAR, feed_scope="feed:1", occurrence_key="uid@2026-01-08",
                          url="https://cal.example.com/event")
    assert a != b and a.method == u.ID_CALENDAR


def test_feed_guid_is_scoped_to_feed():
    a = u.observation_identity(provider="rss", external_id=None, feed_scope="feed:1", guid="123")
    b = u.observation_identity(provider="rss", external_id=None, feed_scope="feed:2", guid="123")
    assert a != b and not a.document_level


def test_news_without_url_falls_back_to_content_hash():
    i = u.choose_identity(record_type=u.RT_NEWS, title="T", content="body")
    assert i.method == u.ID_CONTENT_HASH


def test_google_news_redirect_detected_and_google_url_unwrapped():
    assert u.is_redirect_wrapper("https://news.google.com/rss/articles/CBMi?oc=5")
    assert u.unwrap_redirect("https://www.google.com/url?url=https://x.com/a&sa=t") == "https://x.com/a"


# ---------------------------------------------------------------------------
# Dates (work package 7)
# ---------------------------------------------------------------------------

def test_offset_timestamp_normalizes_to_utc_instant():
    p = d.parse_date("2026-09-30T10:00:00+02:00")
    assert p.value == datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
    assert p.exact and p.status == d.STATUS_OK


def test_invalid_input_yields_null_plus_raw_and_status():
    p = d.parse_date("not a date")
    assert p.value is None and p.raw == "not a date" and p.status == d.STATUS_INVALID


def test_missing_stays_unknown_not_now():
    p = d.parse_date("")
    assert p.value is None and p.status == d.STATUS_MISSING
    assert p.as_fields()["date_provenance"] == d.PROV_UNKNOWN


def test_day_month_year_precision_retained():
    assert d.parse_date("2026-09-30").precision == d.PREC_DAY
    assert d.parse_date("2026-09").precision == d.PREC_MONTH
    assert d.parse_date("2026").precision == d.PREC_YEAR
    assert d.parse_date([[2026, 9]]).precision == d.PREC_MONTH


def test_naive_timestamp_is_unknown_unless_utc_documented():
    assert d.parse_date("2026-09-30T10:00:00").value is None
    p = d.parse_date("2026-09-30T10:00:00", assume_utc=True)
    assert p.value == datetime(2026, 9, 30, 10, tzinfo=timezone.utc) and p.tz_assumed


def test_rfc2822_and_struct_time():
    assert d.parse_date("Tue, 30 Sep 2026 10:00:00 GMT").value == datetime(2026, 9, 30, 10, tzinfo=timezone.utc)
    st = time.gmtime(1790000000)
    assert d.parse_date(st).value == datetime.fromtimestamp(1790000000, tz=timezone.utc)


def test_future_date_is_kept_and_flagged():
    p = d.parse_date("2049-12-31")
    assert p.known and p.is_future()


def test_best_of_prefers_exact_provider_over_model_and_known_over_missing():
    model = d.parse_date("2026-09-30", provenance=d.PROV_MODEL)
    feed = d.parse_date("2026-09-30T08:00:00Z", provenance=d.PROV_FEED)
    assert d.best_of(model, feed) is feed
    assert d.best_of(d.unknown(), model) is model


# ---------------------------------------------------------------------------
# Shared ledger (work packages 20 and 21)
# ---------------------------------------------------------------------------

@pytest.fixture
def ledger(tmp_path):
    return sl.SharedLedger(str(tmp_path / "ledger.sqlite"), tenant="t1")


def test_two_tenants_share_one_daily_budget(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    policy = {"newsapi": {"period": "day", "budget": 4}}
    a = sl.SharedLedger(path, policy=policy, tenant="wbm")
    b = sl.SharedLedger(path, policy=policy, tenant="wileytest")
    sent = 0
    for i in range(6):
        if a.reserve("newsapi", "KEY").ok:
            sent += 1
        if b.reserve("newsapi", "KEY").ok:
            sent += 1
    assert sent == 4
    assert a.reserve("newsapi", "KEY").reason in ("budget", "share")


def test_share_with_borrowing(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    policy = {"newsapi": {"period": "day", "budget": 4}}
    a = sl.SharedLedger(path, policy=policy, tenant="a")
    b = sl.SharedLedger(path, policy=policy, tenant="b")
    # Both seen; share is 2 each. a takes its 2, then asks for a third.
    assert a.reserve("newsapi", "K").ok and b.reserve("newsapi", "K").ok and a.reserve("newsapi", "K").ok
    third = a.reserve("newsapi", "K")
    # b has 1 of its 2 left to claim; used 3 + 1 + 1 claimable = 5 > 4 → refused.
    assert not third.ok and third.reason == "share"
    assert b.reserve("newsapi", "K").ok
    assert not a.reserve("newsapi", "K").ok


def test_first_429_pauses_every_tenant_until_reset(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    policy = {"newsdata": {"period": "day", "budget": None}}
    a = sl.SharedLedger(path, policy=policy, tenant="a")
    b = sl.SharedLedger(path, policy=policy, tenant="b")
    assert a.reserve("newsdata", "K").ok
    until = a.record_response("newsdata", "K", "quota", retry_after_seconds=600, detail="HTTP 429")
    assert until is not None
    r = b.reserve("newsdata", "K")
    assert not r.ok and r.reason == "exhausted" and r.exhausted_until == until
    assert b.exhausted_until("newsdata", "K") == until


def test_ledger_survives_reopen(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    a = sl.SharedLedger(path, policy={"p": {"period": "day", "budget": 10}}, tenant="a")
    a.reserve("p", "K"); a.reserve("p", "K")
    b = sl.SharedLedger(path, policy={"p": {"period": "day", "budget": 10}}, tenant="a")
    assert b.reserve("p", "K").used == 3


def test_ok_response_clears_pause(ledger):
    ledger.record_response("xpoz", "K", "quota", retry_after_seconds=60)
    assert ledger.exhausted_until("xpoz", "K") is not None
    ledger.record_response("xpoz", "K", "ok")
    assert ledger.exhausted_until("xpoz", "K") is None


def test_host_budget_and_pause_shared(tmp_path):
    path = str(tmp_path / "ledger.sqlite")
    hosts = {"reddit.com": {"period": "rolling:60", "budget": 2}}
    a = sl.SharedLedger(path, host_budgets=hosts, tenant="a")
    b = sl.SharedLedger(path, host_budgets=hosts, tenant="b")
    assert a.host_acquire("www.reddit.com").ok and b.host_acquire("reddit.com").ok
    assert not a.host_acquire("reddit.com").ok
    until = b.host_record_429("www.reddit.com", retry_after_seconds=120)
    r = a.host_acquire("old.reddit.com")
    assert not r.ok and r.reason == "exhausted" and r.exhausted_until == until
    assert a.host_acquire("example.com").ok  # no policy, no pause


def test_status_reports_tenants_and_hosts(ledger):
    ledger.reserve("newsapi", "K")
    ledger.host_record_429("reddit.com", retry_after_seconds=30)
    s = ledger.status()
    assert s["providers"][0]["tenants"] == {"t1": 1}
    assert s["hosts"][0]["paused_until"] is not None


def test_parse_retry_after_seconds_and_date():
    assert sl.parse_retry_after("120") == 120.0
    future = (datetime.now(timezone.utc) + timedelta(seconds=90)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert 80 <= sl.parse_retry_after(future) <= 91
    assert sl.parse_retry_after(None) is None


def test_fingerprint_is_short_and_stable():
    assert sl.key_fingerprint("abc") == sl.key_fingerprint("abc") and len(sl.key_fingerprint("abc")) == 12
    assert sl.key_fingerprint("abc") != sl.key_fingerprint("abd")
