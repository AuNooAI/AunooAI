"""Reading and saving brand decisions on the scoped match row.

The decision for an article and a brand topic lives on its
``keyword_article_matches`` rows (one per article and group). Rules from
docs/BRAND_RELEVANCE_SPEC.md, "Storage and decision reuse":

- a row with a valid label keeps it when collectors rediscover the article;
- a row with a legacy verdict and no label keeps the legacy verdict;
- a failed attempt is recorded in ``last_failure`` and never replaces a verdict;
- the article write and the match write commit together, and a save that
  touches no match row fails;
- a corrupt stored label is reported as invalid and never read as a score.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services import brand_decision as bd

logger = logging.getLogger(__name__)

TERMINAL_ARTICLE_STATES = ("approved", "filtered_relevance", "deferred")
RETRY_STATES = ("relevance_check_failed", "deferred")
# Match-row states after which a labelled row is settled even if the article is not.
DONE_MATCH_STATES = ("approved", "filtered_relevance", "quality_failed")


class SaveFailed(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

SCOPED_SQL = """
    SELECT m.id, m.group_id, m.relevance_status, m.brand_relation, m.source_relation,
           m.judge_version, m.decision_evidence::text AS evidence,
           a.ingest_status AS article_status, a.topic AS article_topic
      FROM keyword_article_matches m
      JOIN keyword_groups g ON g.id = m.group_id
      JOIN articles a ON a.uri = m.article_uri
     WHERE m.article_uri = ? AND g.topic = ?
"""


def decision_from_row(row: Dict[str, Any]) -> Optional[bd.Decision]:
    rel = row.get("brand_relation")
    if rel not in bd.LABELS:
        return None
    ev = row.get("evidence") or row.get("decision_evidence") or {}
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except ValueError:
            ev = {}
    return bd.Decision("decided", rel, row.get("source_relation"),
                       provenance=(ev or {}).get("provenance") or "stored",
                       reason=(ev or {}).get("reason") or "", evidence=ev or {},
                       route=(ev or {}).get("route") or "", resolved_model=(ev or {}).get("resolved_model") or "",
                       judge_version=row.get("judge_version") or "")


def classify_stored(rows: List[Dict[str, Any]], topic: str) -> Tuple[str, Optional[bd.Decision], Optional[str]]:
    """(state, decision, article_status) for an article under a brand topic.

    States:
      ``no_row``       no match row for this topic: the brand path does not apply
      ``label_done``   decided under the new contract and settled: leave it alone
      ``label_retry``  decided, but the article's analysis did not finish: reuse
                       the label and retry the analysis, no new judgment
      ``invalid``      a stored label outside the label set: reported, left alone
      ``legacy``       a pre-label verdict (on the match row, or on the article
                       row for sites that never stored per-group verdicts): kept
      ``undecided``    no verdict, a failed attempt, or a deferral: decide now
    """
    if not rows:
        return "no_row", None, None
    art_status = rows[0].get("article_status")
    for r in rows:
        if r.get("brand_relation") is not None and r.get("relevance_status") not in RETRY_STATES:
            d = decision_from_row(r)
            if d is None:
                return "invalid", None, art_status
            if r.get("relevance_status") in DONE_MATCH_STATES or art_status in TERMINAL_ARTICLE_STATES:
                return "label_done", d, art_status
            return "label_retry", d, art_status
    for r in rows:
        if r.get("brand_relation") is None and r.get("relevance_status") in ("approved", "filtered_relevance"):
            return "legacy", None, art_status
    if all(r.get("relevance_status") is None for r in rows) \
            and rows[0].get("article_topic") == topic and art_status in ("approved", "filtered_relevance"):
        return "legacy", None, art_status
    return "undecided", None, art_status


async def stored_state(adb, uri: str, topic: str):
    rows = await adb.fetch_all(SCOPED_SQL, (uri, topic))
    return classify_stored([dict(r) for r in rows], topic)


def reuse_lookup_sync(uri: str):
    """A ``reuse`` callable for brand_decision.decide: a decision stored for
    the same article under exactly the same input key, in any group."""
    def lookup(key: str) -> Optional[bd.Decision]:
        conn = None
        try:
            from sqlalchemy import text
            from app.database import get_database_instance
            conn = get_database_instance()._temp_get_connection()
            row = conn.execute(text("""
                SELECT brand_relation, source_relation, judge_version, decision_evidence::text AS evidence
                  FROM keyword_article_matches
                 WHERE article_uri = :u AND judge_version = :k AND brand_relation IS NOT NULL
                   AND COALESCE(relevance_status, '') NOT IN ('relevance_check_failed', 'deferred')
                 LIMIT 1
            """), {"u": uri, "k": key}).mappings().first()
            return decision_from_row(dict(row)) if row else None
        except Exception as e:  # noqa: BLE001 - reuse is an optimisation, never a blocker
            logger.debug("brand reuse lookup failed for %s: %s", uri[:80], e)
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
    return lookup


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

# Rows this save may write: undecided ones, rows still in flight for this
# pipeline ('pending', or an analysis that failed and is being retried), and
# rows that already carry exactly this decision (same input key). A different
# stored verdict is never overwritten.
_WRITABLE = ("(m.brand_relation IS NULL"
             " OR COALESCE(m.relevance_status, '') IN ('relevance_check_failed', 'deferred', 'pending', 'enrichment_failed')"
             " OR m.judge_version = ?)")


def match_decision_sql(uri: str, topic: str, d: bd.Decision) -> Tuple[str, tuple]:
    """UPDATE for the scoped match rows of a decided or deferred candidate.
    Only undecided rows are written, so a concurrent or earlier verdict wins."""
    status = d.ingest_status
    grade = d.grade
    evidence = json.dumps(d.to_evidence_json(), ensure_ascii=False, default=str)
    failure = json.dumps({"reason": d.failure, "route": d.route}, ensure_ascii=False) if d.failure else None
    q = f"""
        UPDATE keyword_article_matches m
           SET brand_relation = ?, source_relation = ?, judge_version = ?,
               decision_evidence = ?::jsonb, relevance_status = ?, topic_alignment_score = ?,
               scored_at = NOW(), below_threshold = ?,
               last_failure = COALESCE(?::jsonb, m.last_failure)
          FROM keyword_groups g
         WHERE g.id = m.group_id AND g.topic = ? AND m.article_uri = ? AND {_WRITABLE}
    """
    params = (d.brand_relation if d.outcome == "decided" else None, d.source_relation, d.judge_version,
              evidence, status, grade, 0 if status == "approved" else 1, failure, topic, uri,
              d.judge_version or "")
    return q, params


def match_failure_sql(uri: str, topic: str, d: bd.Decision) -> Tuple[str, tuple]:
    """Record an unavailable judgment. Never touches a verdict."""
    failure = json.dumps({"reason": d.failure, "route": d.route, "evidence": d.to_evidence_json()},
                         ensure_ascii=False, default=str)
    q = f"""
        UPDATE keyword_article_matches m
           SET last_failure = ?::jsonb || jsonb_build_object(
                   'attempts', COALESCE((m.last_failure->>'attempts')::int, 0) + 1,
                   'at', to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
               scored_at = NOW(),
               relevance_status = CASE WHEN m.brand_relation IS NULL
                                       THEN 'relevance_check_failed' ELSE m.relevance_status END
          FROM keyword_groups g
         WHERE g.id = m.group_id AND g.topic = ? AND m.article_uri = ?
    """
    return q, (failure, topic, uri)


def article_verdict_sql(article: Dict[str, Any], topic: str, d: bd.Decision) -> Tuple[str, tuple]:
    """Upsert of the article's own verdict for a non-admitted, deferred or
    unavailable candidate. The WHERE keeps another topic's approval intact,
    as save_below_threshold_article does."""
    pub = article.get("publication_date")
    if pub is not None and hasattr(pub, "isoformat"):
        pub = pub.isoformat()
    grade = d.grade if d.grade is not None else 0.0
    q = """
        INSERT INTO articles (uri, title, summary, news_source, publication_date, topic,
                              topic_alignment_score, keyword_relevance_score, confidence_score,
                              overall_match_explanation, analyzed, ingest_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (uri) DO UPDATE SET
            topic_alignment_score = EXCLUDED.topic_alignment_score,
            confidence_score = EXCLUDED.confidence_score,
            overall_match_explanation = EXCLUDED.overall_match_explanation,
            ingest_status = EXCLUDED.ingest_status
        WHERE articles.topic = EXCLUDED.topic
           OR articles.ingest_status IS DISTINCT FROM 'approved'
    """
    params = (article.get("uri"), article.get("title"), article.get("summary"), article.get("news_source"),
              pub, topic, grade, grade, 1.0 if d.outcome == "decided" else 0.0, d.explanation()[:1000],
              False, d.ingest_status)
    return q, params


async def run_transaction(adb, statements: List[Tuple[str, tuple, bool]]) -> List[int]:
    """Execute (query, params, must_touch_rows) in one transaction. A
    statement that must touch rows and touches none rolls the lot back."""
    counts: List[int] = []
    async with adb.get_connection() as conn:
        if getattr(adb, "db_type", "postgresql") != "postgresql":
            raise SaveFailed("brand decisions need PostgreSQL")
        async with conn.transaction():
            for q, params, required in statements:
                q2, p2 = adb._convert_query_params(q, params)
                res = await conn.execute(q2, *p2)
                try:
                    n = int(str(res).split()[-1])
                except (ValueError, IndexError):
                    n = 0
                counts.append(n)
                if required and n == 0:
                    raise SaveFailed(f"no row updated by: {q.split()[0]} {q.split()[1]} ...")
    return counts


async def save_rejection(adb, article: Dict[str, Any], topic: str, d: bd.Decision) -> str:
    """Save a decided-but-not-admitted, deferred or unavailable candidate:
    article verdict and match rows together. Returns 'saved' or 'concurrent'
    when another worker decided the same rows first."""
    if d.outcome == "unavailable":
        mq = match_failure_sql(article["uri"], topic, d)
    else:
        mq = match_decision_sql(article["uri"], topic, d)
    aq = article_verdict_sql(article, topic, d)
    try:
        await run_transaction(adb, [(aq[0], aq[1], False), (mq[0], mq[1], True)])
        return "saved"
    except SaveFailed:
        state, _, _ = await stored_state(adb, article["uri"], topic)
        if state in ("label_done", "label_retry"):
            return "concurrent"
        raise


async def save_admitted(adb, article_query: Tuple[str, tuple], uri: str, topic: str, d: bd.Decision) -> str:
    """Save an admitted candidate: the enrichment UPDATE of the article and
    its match rows, together. Both must touch a row."""
    mq = match_decision_sql(uri, topic, d)
    try:
        await run_transaction(adb, [(article_query[0], article_query[1], True), (mq[0], mq[1], True)])
        return "saved"
    except SaveFailed:
        state, _, _ = await stored_state(adb, uri, topic)
        if state in ("label_done", "label_retry"):
            return "concurrent"
        raise


async def mark_label_status(adb, uri: str, topic: str, status: str) -> int:
    """Move a labelled row's status after a later pipeline step (quality
    check failed, analysis failed). The label itself is never changed here."""
    q = """
        UPDATE keyword_article_matches m SET relevance_status = ?, scored_at = NOW()
          FROM keyword_groups g
         WHERE g.id = m.group_id AND g.topic = ? AND m.article_uri = ? AND m.brand_relation IS NOT NULL
    """
    return await adb.execute_single_update(q, (status, topic, uri))


async def save_label_with_status(adb, uri: str, topic: str, d: bd.Decision, status: str) -> str:
    """Store an admitted label whose article did not finish (quality check
    failed, analysis failed). The article row is not touched; the match row
    carries the label and the given status, so a later cycle neither judges
    again nor loses the label."""
    mq = match_decision_sql(uri, topic, d)
    sq = ("""
        UPDATE keyword_article_matches m SET relevance_status = ?, below_threshold = 1
          FROM keyword_groups g
         WHERE g.id = m.group_id AND g.topic = ? AND m.article_uri = ? AND m.brand_relation IS NOT NULL
    """, (status, topic, uri))
    try:
        await run_transaction(adb, [(mq[0], mq[1], True), (sq[0], sq[1], True)])
        return "saved"
    except SaveFailed:
        state, _, _ = await stored_state(adb, uri, topic)
        if state in ("label_done", "label_retry"):
            return "concurrent"
        raise


async def save_article_verdict_only(adb, article: Dict[str, Any], topic: str, d: bd.Decision) -> int:
    """Bring the article row in line with an already stored label (used when
    a labelled row's article never got its verdict)."""
    aq = article_verdict_sql(article, topic, d)
    counts = await run_transaction(adb, [(aq[0], aq[1], False)])
    return counts[0]
