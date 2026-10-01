"""Work package 7: the analyzer's date extraction is typed and never the
current time; research prefers a provider date and reads stored dates for
cached content."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.analyzers.article_analyzer import ArticleAnalyzer
from app.collectors.dates import PREC_DAY, PROV_MODEL, STATUS_INVALID, STATUS_MISSING
import app.research as research_mod
from app.research import Research, resolve_publication_date


def _analyzer(reply):
    model = Mock()
    model.generate_response = Mock(return_value=reply)
    return ArticleAnalyzer(model, use_cache=False)


def test_model_day_has_day_precision_and_model_provenance():
    res = _analyzer("2026-09-30").extract_publication_date_result("some page text")
    assert res.known
    assert res.value == datetime(2026, 9, 30, tzinfo=timezone.utc)
    assert res.precision == PREC_DAY and not res.exact       # a day, not an exact midnight instant
    assert res.provenance == PROV_MODEL
    assert res.raw == "2026-09-30"


def test_wrapped_model_output_still_parses():
    res = _analyzer("The article was published on 2026-09-30.").extract_publication_date_result("x")
    assert res.known and res.value.date().isoformat() == "2026-09-30" and res.precision == PREC_DAY


def test_empty_and_invalid_output_are_unknown_not_now():
    before = datetime.now(timezone.utc)
    empty = _analyzer("").extract_publication_date_result("x")
    bad = _analyzer("no date found").extract_publication_date_result("x")
    assert not empty.known and empty.status == STATUS_MISSING and empty.provenance == PROV_MODEL
    assert not bad.known and bad.status == STATUS_INVALID and bad.raw == "no date found"
    for r in (empty, bad):
        assert r.value is None
        assert r.iso() is None
    assert _analyzer("").extract_publication_date("x") is None
    assert datetime.now(timezone.utc) >= before  # sanity: nothing above depended on the clock


def test_model_error_is_unknown_not_now():
    model = Mock()
    model.generate_response = Mock(side_effect=RuntimeError("boom"))
    res = ArticleAnalyzer(model, use_cache=False).extract_publication_date_result("x")
    assert res.value is None and res.status == STATUS_INVALID
    assert ArticleAnalyzer(model, use_cache=False).extract_publication_date("x") is None


def test_compat_wrapper_returns_iso_string():
    assert _analyzer("2026-09-30").extract_publication_date("x") == "2026-09-30T00:00:00+00:00"


class _CountingAnalyzer:
    def __init__(self, reply="2026-09-30"):
        self.calls = 0
        self.reply = reply

    def extract_publication_date_result(self, content):
        self.calls += 1
        return _analyzer(self.reply).extract_publication_date_result(content)


def test_provider_date_means_zero_extraction_calls():
    an = _CountingAnalyzer()
    value, prov = resolve_publication_date("2026-09-29T10:00:00Z", "page text", an)
    assert (value, prov) == ("2026-09-29T10:00:00Z", "provider")
    assert an.calls == 0


def test_no_provider_date_calls_the_model_once_and_unknown_stays_none():
    an = _CountingAnalyzer()
    value, prov = resolve_publication_date(None, "page text", an)
    assert value == "2026-09-30T00:00:00+00:00" and prov == PROV_MODEL and an.calls == 1
    bad = _CountingAnalyzer(reply="")
    assert resolve_publication_date("", "page text", bad) == (None, "unknown")
    assert resolve_publication_date(None, "", bad) == (None, "unknown")   # no text: no call
    assert bad.calls == 1


def test_cached_content_returns_stored_publication_date_not_submission_date(monkeypatch):
    rows = {"https://e.com/a": {"publication_date": "2026-01-02", "date_provenance": None,
                                "submission_date": "2026-09-30 10:00:00"}}

    class FakeFacade:
        def __init__(self, db, logger):
            pass

        def get_article_by_uri(self, uri):
            return rows.get(uri)

    monkeypatch.setattr(research_mod, "DatabaseQueryFacade", FakeFacade)
    r = Research.__new__(Research)
    r.db = object()
    assert r.stored_publication_date("https://e.com/a") == ("2026-01-02", "stored")
    assert r.stored_publication_date("https://e.com/missing") == (None, "unknown")
