"""Work package 19: the early relevance gate consults the rejected-candidate
ledger before embedding, records fresh rejections, and leaves other routes
alone."""
import asyncio

import pytest

from app.collectors.url_identity import canonical_url
from app.services import rejected_candidates as rc
from app.services import automated_ingest_service as ais
from tests._cdq_ingest_fakes import make_service, full_topic, article, FakeLedger


@pytest.fixture(autouse=True)
def ledger_on(monkeypatch):
    FakeLedger.instances.clear()
    monkeypatch.setattr(ais._rejected, "enabled", lambda: True)
    yield
    FakeLedger.instances.clear()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_ledger_hit_skips_scoring_and_does_not_rewrite_the_row(monkeypatch):
    url = "https://example.com/story?utm_source=x"
    hit = rc.LedgerHit(canonical_url(url), 0.12, 0.5, None)
    monkeypatch.setattr(ais._rejected, "RejectedCandidateLedger",
                        lambda db: FakeLedger(db, hits={canonical_url(url): hit}))
    svc = make_service({"T": full_topic()})

    out = _run(svc.process_articles_batch([article(url)], "T", ["alpha"], group_id=7))

    assert out["already_rejected"] == 1
    assert out["processed"] == 1
    assert svc.score_calls == []                      # no embedding
    assert svc.async_db.saved_below == []             # the row from the first rejection stands
    ledger = FakeLedger.instances[0]
    assert ledger.lookups[0][1] == 7
    assert ledger.records == []


def test_ledger_miss_scores_and_records_the_rejection(monkeypatch):
    monkeypatch.setattr(ais._rejected, "RejectedCandidateLedger", lambda db: FakeLedger(db))
    url = "https://example.com/other"
    svc = make_service({"T": full_topic()}, score=0.1, threshold=0.5)

    out = _run(svc.process_articles_batch([article(url)], "T", ["alpha", "beta"], group_id=7))

    assert out["already_rejected"] == 0
    assert svc.score_calls == [url]
    assert svc.async_db.saved_below[0]["ingest_status"] == "filtered_relevance"
    ledger = FakeLedger.instances[0]
    assert len(ledger.records) == 1
    rec_url, group_id, version, score, threshold = ledger.records[0]
    assert (rec_url, group_id, score, threshold) == (url, 7, 0.1, 0.5)
    assert version == rc.gate_version(["alpha", "beta"], 0.5)


def test_version_changes_when_terms_or_threshold_change():
    base = rc.gate_version(["alpha", "beta"], 0.5)
    assert rc.gate_version(["beta", "alpha"], 0.5) == base          # order does not matter
    assert rc.gate_version(["alpha", "gamma"], 0.5) != base         # terms do
    assert rc.gate_version(["alpha", "beta"], 0.4) != base          # threshold does


def test_rss_route_skips_the_ledger_and_an_accepted_article_is_forgotten(monkeypatch):
    forgotten = []

    class Forgetting(FakeLedger):
        def forget(self, url, group_id=None):
            forgotten.append(url)
            return 1

    monkeypatch.setattr(ais._rejected, "RejectedCandidateLedger", lambda db: Forgetting(db))
    url = "https://example.com/rss-accepted"
    svc = make_service({"T": full_topic()}, score=0.9, threshold=0.5)
    rss_article = article(url)
    rss_article["url"] = url
    rss_article["published_date"] = "2026-09-30"

    out = _run(svc.process_articles_batch([rss_article], "T", ["alpha"], route="rss"))

    assert out["saved"] == 1
    assert out["already_rejected"] == 0
    # No lookup for the RSS route; the accepted article drops any stale keyword rejection.
    assert all(l.lookups == [] for l in FakeLedger.instances)
    assert forgotten == [url]


def test_keyword_route_resolves_group_from_topic_when_not_passed(monkeypatch):
    monkeypatch.setattr(ais._rejected, "RejectedCandidateLedger", lambda db: FakeLedger(db))
    svc = make_service({"T": full_topic()})
    svc._resolve_group_id_for_topic = lambda topic: 42

    _run(svc.process_articles_batch([article("https://example.com/a")], "T", ["alpha"]))

    assert FakeLedger.instances[0].lookups[0][1] == 42


def test_ledger_disabled_means_no_lookup(monkeypatch):
    monkeypatch.setattr(ais._rejected, "enabled", lambda: False)
    monkeypatch.setattr(ais._rejected, "RejectedCandidateLedger", lambda db: FakeLedger(db))
    svc = make_service({"T": full_topic()})

    _run(svc.process_articles_batch([article("https://example.com/a")], "T", ["alpha"], group_id=7))

    assert FakeLedger.instances == []
    assert svc.score_calls == ["https://example.com/a"]
