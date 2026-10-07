"""Relevance decisions and readers (docs/pipelines/08_INGEST_FIX_SPEC.md WP4/WP5a; M2).

- The Jev and cross-encoder tiers accept on their own criterion and no
  longer raise the score to the threshold.
- The quick and final gates use the same group threshold.
- Readers honour a recorded decision, keep the old score rule for legacy
  rows, and never show a failed relevance check.
- The SQL predicate and the Python check agree on the same rows.
"""
import asyncio

import pytest

from app.services import hybrid_relevance_service as hrs
from app.services import automated_ingest_service as ais
from app.services import article_visibility as av


def _svc(monkeypatch, *, embed, classifier, jev_on_topic=None, ce=None, llm=None):
    svc = object.__new__(hrs.HybridRelevanceService)
    svc._embedding_loaded = True
    svc._classifier_loaded = True
    svc._compute_embedding_similarity = lambda *a, **k: embed
    svc._compute_classifier_score = lambda *a, **k: classifier
    svc._compute_cross_encoder_score = lambda *a, **k: ce
    svc._compute_llm_score = lambda *a, **k: llm
    svc._compute_jev_shadow = lambda *a, **k: (
        None if jev_on_topic is None else
        {"jev_on_topic": jev_on_topic, "jev_score": jev_on_topic, "jev_confidence": 0.9})
    monkeypatch.setattr(hrs, "JEV_SHADOW", False, raising=False)
    return svc


def test_jev_accept_keeps_its_criterion_and_the_measured_score(monkeypatch):
    """Jev on_topic 0.85 with a group threshold of 0.9: accepted, as before
    (JEV_ACCEPT_MIN 0.8), but the stored score is the local one, not 0.9."""
    monkeypatch.setattr(hrs, "JEV_ACCEPT", True)
    monkeypatch.setattr(hrs, "JEV_ACCEPT_MIN", 0.8)
    svc = _svc(monkeypatch, embed=0.5, classifier=0.5, jev_on_topic=0.85, llm=0.1)
    out = svc.score_relevance("AI", "title", "summary text", threshold=0.9, use_llm_fallback=True)
    assert out["accepted_by"] == "jev_accept" and out["relevant"] is True
    assert out["score"] < 0.9 and out["llm_score"] is None


def test_jev_below_its_criterion_falls_through_to_the_numeric_decision(monkeypatch):
    monkeypatch.setattr(hrs, "JEV_ACCEPT", True)
    monkeypatch.setattr(hrs, "JEV_ACCEPT_MIN", 0.8)
    svc = _svc(monkeypatch, embed=0.5, classifier=0.5, jev_on_topic=0.6, llm=0.3)
    out = svc.score_relevance("AI", "title", "summary text", threshold=0.4, use_llm_fallback=True)
    assert not out["accepted_by"] and out["score"] == 0.3 and out["relevant"] is False


def test_ce_accept_records_acceptance_without_clamping(monkeypatch):
    monkeypatch.setattr(hrs, "USE_CE_TIER", True)
    monkeypatch.setattr(hrs, "CE_HIGH", 0.05)
    monkeypatch.setattr(hrs, "JEV_ACCEPT", False)
    svc = _svc(monkeypatch, embed=0.5, classifier=0.5, ce=0.2)
    out = svc.score_relevance("AI", "title", "summary text", threshold=0.7, use_llm_fallback=False)
    assert out["accepted_by"] == "ce_accept" and out["relevant"] is True and out["score"] < 0.7


@pytest.mark.parametrize("score,threshold,expected", [
    (0.39, 0.4, False), (0.4, 0.4, True), (0.26, 0.25, True), (0.89, 0.9, False)])
def test_numeric_decisions_use_the_group_threshold(score, threshold, expected):
    res = {"relevance_score": score, "_hybrid_method": "embedding+classifier"}
    assert ais.relevance_accepted(res, threshold) is expected
    ev = ais.relevance_evidence(res, threshold, group_id=16)
    assert ev["relevance_accepted_applied"] is expected and ev["relevance_threshold_applied"] == threshold
    assert ev["relevance_decision_group_id"] == 16 and ev["relevance_policy_version"] == av.POLICY_VERSION


def test_engine_accept_is_recorded_as_such():
    res = {"relevance_score": 0.5, "_accepted_by": "jev_accept", "_engine_scores": {"jev_on_topic": 0.85}}
    ev = ais.relevance_evidence(res, 0.9)
    assert ev["relevance_accepted_applied"] is True and ev["relevance_decision_engine"] == "jev_accept"
    assert ev["relevance_engine_scores"] == {"jev_on_topic": 0.85}


def test_quick_and_final_gates_get_the_same_group_threshold(monkeypatch):
    """A group threshold of 0.25 (group 16) reaches both gates; until 7 Oct
    the final gate ignored it for non-brand topics."""
    from tests._cdq_ingest_fakes import make_service, full_topic, article
    svc = make_service({"T": full_topic()}, score=0.3, threshold=0.4)
    seen = []
    inner = svc._score_article_relevance_async

    async def spy(a, topic, keywords, threshold=None):
        seen.append(threshold)
        return await inner(a, topic, keywords, threshold=threshold)
    svc._score_article_relevance_async = spy
    out = asyncio.new_event_loop().run_until_complete(svc.process_articles_batch(
        [article("https://e.com/g16")], "T", ["k"], route="manual",
        relevance_threshold_override=0.25, group_id=16))
    assert seen == [0.25, 0.25] and out["saved"] == 1
    ev = svc.async_db.decisions["https://e.com/g16"]
    assert ev["relevance_threshold_applied"] == 0.25 and ev["relevance_accepted_applied"] is True


def test_a_failed_relevance_check_stores_no_scores(monkeypatch):
    from tests._cdq_ingest_fakes import make_service, full_topic, article
    svc = make_service({"T": full_topic()}, score=0.9)

    async def boom(*a, **k):
        raise RuntimeError("no engine answered")
    svc._score_article_relevance_async = boom
    asyncio.new_event_loop().run_until_complete(svc.process_articles_batch(
        [article("https://e.com/f")], "T", ["k"], route="manual"))
    row = svc.async_db.saved_below[-1]
    assert row["ingest_status"] == "relevance_check_failed" and row["topic_alignment_score"] is None
    assert svc.async_db.relevance_failures[0][0] == "https://e.com/f"


# --- readers -----------------------------------------------------------------

ROWS = [
    # (name, row, readable)
    ("legacy above floor", dict(topic_alignment_score=0.5), True),
    ("legacy below floor", dict(topic_alignment_score=0.3), False),
    ("legacy with its own threshold", dict(topic_alignment_score=0.3, relevance_threshold_applied=0.25), True),
    ("manual, never scored", dict(topic_alignment_score=None, ingest_status="manual"), True),
    ("failed check, NULL score", dict(topic_alignment_score=None, ingest_status="relevance_check_failed"), False),
    ("enrichment failed", dict(topic_alignment_score=0.9, ingest_status="enrichment_failed"), False),
    ("decided accept below 0.4", dict(topic_alignment_score=0.3, relevance_accepted_applied=True,
                                      relevance_threshold_applied=0.25, ingest_status="approved"), True),
    ("decided reject above 0.4", dict(topic_alignment_score=0.5, relevance_accepted_applied=False,
                                      relevance_threshold_applied=0.6, ingest_status="filtered_relevance"), False),
    ("jev accept, low score", dict(topic_alignment_score=0.2, relevance_accepted_applied=True,
                                   relevance_decision_engine="jev_accept", ingest_status="approved"), True),
]


@pytest.mark.parametrize("name,row,readable", ROWS, ids=[r[0] for r in ROWS])
def test_python_rule(name, row, readable):
    full = {"ingest_status": None, "source_type": None, "duplicate_of": None, "topic": "AI",
            "relevance_accepted_applied": None, "relevance_threshold_applied": None, **row}
    assert av.is_readable(full) is readable


def _db():
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        conn = db._temp_get_connection()
        return db, conn
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")


def test_sql_and_python_agree():
    """The SQL predicate over the same rows in a temporary table gives the
    same answers as is_readable, including a copy whose original was
    rejected (shown) and a copy whose original is readable (hidden)."""
    from sqlalchemy import text
    db, conn = _db()
    try:
        conn.execute(text("CREATE TEMP TABLE articles (LIKE public.articles INCLUDING DEFAULTS) ON COMMIT DROP"))
        cols = ["uri", "topic", "topic_alignment_score", "ingest_status", "relevance_accepted_applied",
                "relevance_threshold_applied", "relevance_decision_engine", "duplicate_of", "source_type"]
        rows = []
        for i, (name, row, readable) in enumerate(ROWS):
            base = dict(uri=f"u{i}", topic="AI", duplicate_of=None, source_type=None,
                        ingest_status=None, relevance_accepted_applied=None,
                        relevance_threshold_applied=None, relevance_decision_engine=None)
            rows.append(({**base, **row}, readable))
        rows.append((dict(uri="copy-of-rejected", topic="AI", topic_alignment_score=0.9, duplicate_of="u1",
                          ingest_status="approved", relevance_accepted_applied=True,
                          relevance_threshold_applied=0.4, relevance_decision_engine=None, source_type=None), True))
        rows.append((dict(uri="copy-of-readable", topic="AI", topic_alignment_score=0.9, duplicate_of="u0",
                          ingest_status="approved", relevance_accepted_applied=True,
                          relevance_threshold_applied=0.4, relevance_decision_engine=None, source_type=None), False))
        for r, _ in rows:
            conn.execute(text(f"INSERT INTO articles ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"),
                         {c: r.get(c) for c in cols})
        got = {u for (u,) in conn.execute(text(f"SELECT uri FROM articles WHERE {av.readable_sql('articles')}"))}
        want = {r["uri"] for r, readable in rows if readable}
        assert got == want
        # Python agrees on every row it can judge alone (copies need SQL).
        for r, readable in rows:
            if not r.get("duplicate_of"):
                assert av.is_readable(r) is readable, r["uri"]
    finally:
        conn.rollback()
        conn.close()
