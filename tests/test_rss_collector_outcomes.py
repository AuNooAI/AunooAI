"""RSSCollector.fetch_feed_result: one structured outcome per fetch.

Work packages 2, 7 and 29 of docs/COLLECTOR_DATA_QUALITY_SPEC.md. No
network: ``httpx.AsyncClient.get`` is replaced with a function that hands
back a prepared ``httpx.Response`` or raises.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.collectors import contracts as c
from app.collectors import dates
from app.collectors import rss_collector as rc

FEED_URL = "https://feeds.example.test/rss.xml"

RSS_HEAD = '<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>T</title>'
RSS_TAIL = "</channel></rss>"


def _item(n: int, pub: str | None = "Fri, 14 Aug 2026 09:07:52 GMT", title: str | None = None) -> str:
    date = f"<pubDate>{pub}</pubDate>" if pub else ""
    return (f"<item><title>{title or f'Entry {n}'}</title>"
            f"<link>https://x.test/{n}</link>{date}</item>")


def _feed(items: str) -> str:
    return RSS_HEAD + items + RSS_TAIL


def _response(status: int = 200, *, content: bytes | None = None, text: str | None = None,
              headers: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", FEED_URL)
    if content is not None:
        return httpx.Response(status, content=content, headers=headers or {}, request=request)
    return httpx.Response(status, text=text or "", headers=headers or {}, request=request)


def _serve(monkeypatch, response=None, *, raises: BaseException | None = None):
    """Make every client.get return ``response`` (or raise) and record the
    request headers."""
    seen = {}

    async def fake_get(self, url, headers=None, follow_redirects=True, **kw):
        seen["url"] = url
        seen["headers"] = dict(headers or {})
        if raises is not None:
            raise raises
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    return seen


def _fetch(**kw) -> c.CollectionResult:
    return asyncio.run(rc.RSSCollector().fetch_feed_result(FEED_URL, topic="t", **kw))


# ---------------------------------------------------------------------------
# Work package 29: XML hygiene and partial parses
# ---------------------------------------------------------------------------


def test_bom_before_declaration_parses_cleanly(monkeypatch):
    body = b"\xef\xbb\xbf" + _feed(_item(1)).encode("utf-8")
    _serve(monkeypatch, _response(content=body, headers={"ETag": '"v1"'}))
    res = _fetch()
    assert res.succeeded
    assert not res.parse_partial
    assert len(res.items) == 1
    assert res.counts.received == 1 and res.counts.invalid == 0
    assert res.proposed_validators == {"etag": '"v1"'}
    assert res.may_advance_checkpoint


def test_leading_whitespace_before_declaration_parses_cleanly(monkeypatch):
    # Raw, this is the "XML or text declaration not at start of entity"
    # case: 47 warnings in seven days.
    _serve(monkeypatch, _response(text="\r\n\r\n   " + _feed(_item(1))))
    res = _fetch()
    assert res.succeeded and not res.parse_partial and len(res.items) == 1
    assert "hygiene_retry" not in res.diagnostics


def test_comment_before_declaration_is_retried_once_after_cutting(monkeypatch):
    _serve(monkeypatch, _response(text="<!-- served by cdn -->\n" + _feed(_item(1))))
    res = _fetch()
    assert res.succeeded and not res.parse_partial and len(res.items) == 1
    assert res.diagnostics.get("hygiene_retry") is True


def test_invalid_token_yields_entries_marks_partial_and_offers_no_validators(monkeypatch):
    # An unescaped ampersand inside a title: "not well-formed (invalid
    # token)", 139 times in seven days. feedparser recovers the entries.
    body = _feed(_item(1) + _item(2, title="B & C") + _item(3))
    _serve(monkeypatch, _response(text=body, headers={"ETag": '"v2"', "Last-Modified": "x"}))
    res = _fetch()
    assert res.items, "valid entries are still returned"
    assert res.parse_partial is True
    assert res.status == c.STATUS_PARTIAL
    assert res.truncated_reason == c.TRUNC_PARSE_PARTIAL
    assert res.proposed_validators == {}, "no ETag: the next poll must see the full response"
    assert not res.may_advance_checkpoint
    assert "invalid token" in res.diagnostics["bozo"]
    assert res.diagnostics["entries_recovered"] == len(res.items)


def test_document_with_no_feed_structure_is_a_parse_failure(monkeypatch):
    for body in ("", "<html><body>Not a feed</body></html>", '{"items": []}'):
        _serve(monkeypatch, _response(text=body))
        res = _fetch()
        assert res.failed, body
        assert res.error_code == c.ERR_PARSE
        assert res.error_message and "feeds.example.test" in res.error_message
        assert res.items == []
        assert not res.may_advance_checkpoint


def test_malformed_xml_with_no_entries_is_a_parse_failure(monkeypatch):
    _serve(monkeypatch, _response(text='<?xml version="1.0"?><rss><channel><title>T</title><item>'))
    res = _fetch()
    assert res.failed and res.error_code == c.ERR_PARSE
    assert "SAXParseException" in res.error_message


# ---------------------------------------------------------------------------
# Work package 2: complete collection
# ---------------------------------------------------------------------------


def test_valid_empty_feed_is_a_success_that_may_advance(monkeypatch):
    _serve(monkeypatch, _response(text=_feed(""), headers={"ETag": '"empty"'}))
    res = _fetch()
    assert res.succeeded and res.items == [] and not res.parse_partial
    assert res.may_advance_checkpoint
    assert res.proposed_validators["etag"] == '"empty"'
    assert res.counts.received == 0


def test_304_is_a_success_with_no_items_and_sends_validators(monkeypatch):
    seen = _serve(monkeypatch, _response(304, headers={"ETag": '"same"'}))
    res = _fetch(etag='"same"', last_modified="Mon, 01 Sep 2026 00:00:00 GMT")
    assert seen["headers"]["If-None-Match"] == '"same"'
    assert seen["headers"]["If-Modified-Since"] == "Mon, 01 Sep 2026 00:00:00 GMT"
    assert res.succeeded and res.items == []
    assert res.diagnostics["not_modified"] is True
    assert res.proposed_validators["etag"] == '"same"'
    assert res.proposed_validators["last_modified"] == "Mon, 01 Sep 2026 00:00:00 GMT"


def test_120_entry_feed_returns_all_120(monkeypatch):
    body = _feed("".join(_item(n) for n in range(120)))
    _serve(monkeypatch, _response(text=body))
    res = _fetch()
    assert len(res.items) == 120
    assert res.counts.received == 120
    # The list wrapper no longer stops at 50 either.
    assert len(asyncio.run(rc.RSSCollector().fetch_feed(FEED_URL, topic="t"))) == 120


def test_max_entries_is_only_a_caller_limit(monkeypatch):
    body = _feed("".join(_item(n) for n in range(10)))
    _serve(monkeypatch, _response(text=body))
    assert len(_fetch(max_entries=3).items) == 3
    assert len(_fetch(max_entries=None).items) == 10


def test_since_is_advisory_and_drops_nothing(monkeypatch):
    body = _feed(_item(1, pub="Fri, 14 Aug 2026 09:07:52 GMT")
                 + _item(2, pub="Mon, 01 Jan 2024 00:00:00 GMT"))
    _serve(monkeypatch, _response(text=body))
    res = _fetch(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert len(res.items) == 2
    older = [a for a in res.items if a.get("_older_than_since")]
    assert [a["url"] for a in older] == ["https://x.test/2"]
    assert res.diagnostics["older_than_since"] == 1


def test_entries_without_title_or_link_are_counted_invalid(monkeypatch):
    body = _feed(_item(1) + "<item><title></title><link>https://x.test/9</link></item>"
                 + "<item><title>No link</title></item>")
    _serve(monkeypatch, _response(text=body))
    res = _fetch()
    assert len(res.items) == 1
    assert res.counts.received == 3 and res.counts.invalid == 2


# ---------------------------------------------------------------------------
# Work package 7: dates
# ---------------------------------------------------------------------------


def test_missing_date_is_none_not_now(monkeypatch):
    _serve(monkeypatch, _response(text=_feed(_item(1, pub=None))))
    res = _fetch()
    art = res.items[0]
    assert art["published_date"] is None
    assert art["date_provenance"] == dates.PROV_UNKNOWN
    assert art["publication_date_precision"] is None
    assert art["published_at_raw"] is None


def test_unparseable_date_keeps_raw_and_is_unknown(monkeypatch):
    _serve(monkeypatch, _response(text=_feed(_item(1, pub="last Tuesday-ish"))))
    res = _fetch()
    art = res.items[0]
    assert art["published_date"] is None
    assert art["published_at_raw"] == "last Tuesday-ish"
    assert art["date_provenance"] == dates.PROV_UNKNOWN
    assert art["raw_data"]["date_parse_status"] == dates.STATUS_INVALID


def test_feed_date_is_utc_with_feed_provenance_and_second_precision(monkeypatch):
    _serve(monkeypatch, _response(text=_feed(_item(1))))
    art = _fetch().items[0]
    assert art["published_date"] == "2026-08-14T09:07:52+00:00"
    assert art["published_at_raw"] == "Fri, 14 Aug 2026 09:07:52 GMT"
    assert art["date_provenance"] == dates.PROV_FEED
    assert art["publication_date_precision"] == dates.PREC_SECOND


# ---------------------------------------------------------------------------
# Errors: classified, never empty, naming class and host
# ---------------------------------------------------------------------------


def test_http_404_is_a_non_retryable_4xx_naming_host(monkeypatch):
    _serve(monkeypatch, _response(404, text="gone"))
    res = _fetch()
    assert res.failed and res.error_code == c.ERR_HTTP_4XX and not res.retryable
    assert "HTTPStatusError" in res.error_message
    assert "HTTP 404" in res.error_message and "feeds.example.test" in res.error_message
    assert res.diagnostics["http_status"] == 404


def test_429_carries_retry_after_for_the_host_budget(monkeypatch):
    _serve(monkeypatch, _response(429, text="slow down", headers={"Retry-After": "120"}))
    res = _fetch()
    assert res.failed and res.error_code == c.ERR_QUOTA and res.retryable
    assert res.diagnostics["retry_after"] == "120"
    assert res.diagnostics["http_status"] == 429


def test_timeout_names_the_exception_class_not_an_empty_string(monkeypatch):
    _serve(monkeypatch, raises=httpx.ReadTimeout("", request=httpx.Request("GET", FEED_URL)))
    res = _fetch()
    assert res.failed and res.error_code == c.ERR_TIMEOUT and res.retryable
    assert "ReadTimeout" in res.error_message and "feeds.example.test" in res.error_message


def test_list_wrapper_raises_value_error_on_failure_as_before(monkeypatch):
    _serve(monkeypatch, _response(500, text="boom"))
    with pytest.raises(ValueError):
        asyncio.run(rc.RSSCollector().fetch_feed(FEED_URL, topic="t"))


def test_interval_end_is_fixed_at_run_start(monkeypatch):
    _serve(monkeypatch, _response(text=_feed(_item(1))))
    before = datetime.now(timezone.utc)
    res = _fetch(since=before - timedelta(days=1))
    assert res.interval_start == before - timedelta(days=1)
    assert res.interval_end is not None and before <= res.interval_end <= res.finished_at
    assert res.provider == "rss" and res.scope == FEED_URL
