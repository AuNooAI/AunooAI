"""Work package 22: configuration faults quarantine the article without a
model call; article faults count attempts; the sweep retries the right rows."""
import asyncio
from unittest.mock import Mock

import pytest

from app.analyzers.article_analyzer import ArticleAnalyzer, ArticleAnalyzerError, ConfigurationFault
from app.services import automated_ingest_service as ais
from app.services.automated_ingest_service import configuration_block_reason
from app.services.async_db import AsyncDatabase, build_enrichment_update
from app.tasks import enrichment_retry_sweep as sweep
from tests._cdq_ingest_fakes import make_service, full_topic, article, FakeLedger


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def no_ledger(monkeypatch):
    monkeypatch.setattr(ais._rejected, "enabled", lambda: False)


# --- configuration_block_reason ------------------------------------------------

def test_block_reason_names_topic_and_missing_list():
    cfg = full_topic("Interalogistics trends")
    cfg["future_signals"] = []
    assert configuration_block_reason(cfg) == "topic 'Interalogistics trends': future_signals list is empty"


def test_block_reason_none_for_a_complete_topic_and_set_for_disabled():
    assert configuration_block_reason(full_topic()) is None
    cfg = full_topic("X")
    cfg["enrichment_disabled"] = True
    assert "enrichment disabled" in configuration_block_reason(cfg)
    assert configuration_block_reason(None) == "topic configuration missing"


# --- the ingest path -------------------------------------------------------------

def test_empty_future_signals_quarantines_with_topic_named_and_no_model_call():
    cfg = full_topic("T")
    cfg["future_signals"] = []
    svc = make_service({"T": cfg})

    out = _run(svc.process_articles_batch([article("https://e.com/1"), article("https://e.com/2")], "T", ["k"], route="manual"))

    assert out["configuration_blocked"] == 2
    assert svc.score_calls == [] and svc.analyze_calls == []
    saved = svc.async_db.saved_below
    assert len(saved) == 2
    assert {s["ingest_status"] for s in saved} == {"quarantined_config"}
    assert all("topic 'T'" in s["enrichment_block_reason"] and "future_signals" in s["enrichment_block_reason"]
               for s in saved)


def test_complete_topic_is_not_quarantined():
    svc = make_service({"T": full_topic()}, score=0.9)
    out = _run(svc.process_articles_batch([article("https://e.com/1")], "T", ["k"], route="manual"))
    assert out["configuration_blocked"] == 0
    assert out["saved"] == 1
    assert svc.analyze_calls == ["https://e.com/1"]


def test_article_fault_counts_an_attempt_and_stays_enrichment_failed():
    svc = make_service({"T": full_topic()})
    out = _run(svc.process_articles_batch([article("https://e.com/no-text", summary="")], "T", ["k"], route="manual"))
    assert out["configuration_blocked"] == 0
    saved = svc.async_db.saved_below[0]
    assert saved["ingest_status"] == "enrichment_failed"
    assert saved["_enrichment_attempt"] == 1
    assert svc.analyze_calls == []


def test_analyzer_configuration_fault_during_analysis_quarantines_not_fails():
    svc = make_service({"T": full_topic()}, score=0.9)

    async def _analyze(article_data, topic):
        article_data["_configuration_fault"] = "Future signals list cannot be empty"
        return article_data

    svc._analyze_article_content_async = _analyze
    out = _run(svc.process_articles_batch([article("https://e.com/1")], "T", ["k"], route="manual"))
    assert out["configuration_blocked"] == 1
    saved = svc.async_db.saved_below[0]
    assert saved["ingest_status"] == "quarantined_config"
    assert saved["enrichment_block_reason"] == "topic 'T': Future signals list cannot be empty"


# --- analyzer raises a distinct fault --------------------------------------------

def test_analyzer_raises_configuration_fault_for_empty_lists():
    analyzer = ArticleAnalyzer(Mock(), use_cache=False)
    with pytest.raises(ConfigurationFault) as exc:
        analyzer.analyze_content("text", "title", "src", "https://e.com", 50, "neutral", "informative",
                                 ["c"], [], ["s"], ["t"], ["d"])
    assert "Future signals" in str(exc.value)
    assert issubclass(ConfigurationFault, ArticleAnalyzerError)
    # an article fault is still the plain error
    with pytest.raises(ArticleAnalyzerError) as exc2:
        analyzer.analyze_content("", "title", "src", "https://e.com", 50, "neutral", "informative",
                                 ["c"], ["f"], ["s"], ["t"], ["d"])
    assert not isinstance(exc2.value, ConfigurationFault)


# --- persistence statements -----------------------------------------------------

def test_save_below_threshold_carries_block_reason_and_attempt():
    adb = AsyncDatabase.__new__(AsyncDatabase)
    adb.db_type = "postgresql"
    captured = {}

    async def _exec(query, params=()):
        captured["query"] = query
        captured["params"] = params
        return 1

    adb.execute_single_update = _exec
    ok = _run(adb.save_below_threshold_article({
        "uri": "https://e.com/1", "topic": "T", "ingest_status": "enrichment_failed", "_enrichment_attempt": 1,
    }))
    assert ok
    q, p = captured["query"], captured["params"]
    assert q.count("$") >= 14 and "$14" in q
    assert len(p) == 14
    assert p[11] == "enrichment_failed" and p[12] is None and p[13] == 1
    assert "enrichment_attempts = COALESCE(articles.enrichment_attempts, 0) + $14" in q
    assert "first_seen_at = COALESCE(articles.first_seen_at, NOW())" in q


def test_enrichment_update_persists_extraction_and_clears_block_reason():
    q, p = build_enrichment_update({"uri": "u", "topic": "T", "topic_alignment_score": 0.8,
                                    "extraction_status": "ok", "content_kind": "full_text"})
    assert "extraction_status = COALESCE(?, extraction_status)" in q
    assert "content_kind = COALESCE(?, content_kind)" in q
    assert "enrichment_block_reason = ?" in q
    assert "ok" in p and "full_text" in p


# --- sweep selection -------------------------------------------------------------

def test_should_retry_predicate():
    failed = lambda n: {"ingest_status": "enrichment_failed", "enrichment_attempts": n}
    assert sweep.should_retry(failed(0), block_reason_now=None, attempts_cap=3)
    assert sweep.should_retry(failed(2), block_reason_now=None, attempts_cap=3)
    assert not sweep.should_retry(failed(3), block_reason_now=None, attempts_cap=3)
    assert not sweep.should_retry(failed(0), block_reason_now="topic 'T': categories list is empty", attempts_cap=3)
    quarantined = {"ingest_status": "quarantined_config", "enrichment_attempts": 9}
    assert sweep.should_retry(quarantined, block_reason_now=None)
    assert not sweep.should_retry(quarantined, block_reason_now="still empty")
    assert not sweep.should_retry({"ingest_status": "approved"}, block_reason_now=None)


def test_select_candidates_respects_budget_and_block_state():
    good = full_topic("Good")
    bad = full_topic("Bad")
    bad["categories"] = []
    rows = [
        {"uri": "a", "topic": "Good", "ingest_status": "quarantined_config", "enrichment_attempts": 0},
        {"uri": "b", "topic": "Bad", "ingest_status": "quarantined_config", "enrichment_attempts": 0},
        {"uri": "c", "topic": "Good", "ingest_status": "enrichment_failed", "enrichment_attempts": 3},
        {"uri": "d", "topic": "Good", "ingest_status": "enrichment_failed", "enrichment_attempts": 1},
        {"uri": "e", "topic": "Good", "ingest_status": "enrichment_failed", "enrichment_attempts": 0},
    ]
    selected, deferred, reasons = sweep.select_candidates(rows, {"Good": good, "Bad": bad}, budget=2, attempts_cap=3)
    assert [r["uri"] for r in selected] == ["a", "d"]
    assert deferred == 3
    assert reasons["Bad"].startswith("topic 'Bad': categories")
    assert reasons["Good"] is None


def test_sweep_once_runs_selected_rows_through_the_service(monkeypatch):
    rows = [
        {"uri": "https://e.com/q", "topic": "T", "ingest_status": "quarantined_config", "enrichment_attempts": 0,
         "title": "t", "news_source": "s", "publication_date": None, "summary": "body"},
        {"uri": "https://e.com/f3", "topic": "T", "ingest_status": "enrichment_failed", "enrichment_attempts": 3,
         "title": "t", "news_source": "s", "publication_date": None, "summary": "body"},
    ]
    monkeypatch.setattr(sweep, "_fetch_waiting_rows", lambda db, limit: rows)
    monkeypatch.setenv("ENRICHMENT_MAX_ATTEMPTS", "3")

    class Svc:
        calls = []

        async def process_articles_batch(self, articles, topic, keywords, **kw):
            Svc.calls.append((topic, [a["uri"] for a in articles], kw.get("route")))
            return {"saved": 1, "configuration_blocked": 0, "already_rejected": 0, "errors": []}

    class Db:
        class facade:
            @staticmethod
            def get_monitored_keywords_for_topic(params):
                return ["k"]

    out = _run(sweep.sweep_once(Db(), budget=10, service=Svc(), configs={"T": full_topic()}, record=False))
    assert Svc.calls == [("T", ["https://e.com/q"], "enrichment_retry")]
    assert out["selected"] == 1 and out["deferred"] == 1 and out["enriched"] == 1
