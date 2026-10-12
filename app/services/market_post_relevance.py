"""The relevance assessment for vendor LinkedIn posts, against the market.

News and the vendors' own web pages reach a market through ingest, which
scores each one against the market's topic and records the verdict. Vendor
LinkedIn posts do not: ``market_collect.land_article`` files them under the
vendor's own Brand Watch topic with ``topic_alignment_score = 1.0``, so no
post was ever asked whether it is about the market. LiteLLM is in the AI
Security market for its gateway's security controls, and its posts on
self-hosted model routing, decision-model support and an agent-log reader all
went to aisecwire.com as product launches (12 Oct 2026).

This runs the same assessment ingest uses
(``AutomatedIngestService.score_article_relevance``, the market group's
threshold, ``relevance_evidence`` for the decision) on each post the review
judged worth showing, and stores the verdict on the post's market row, under
``bw_market_articles.review_check.relevance``. The article row is left alone,
because the post is the vendor's own coverage in Brand Watch whatever the
market thinks of it. The market corpus reader hides a post whose verdict is a
reject; an unread post shows, so an assessment outage cannot empty the page.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Posts assessed per run. The first run on a market works through its
#: backlog a few hundred at a time; after that a run sees the day's posts.
LIMIT = 300


def market_topic(market: Dict[str, Any]) -> Optional[str]:
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = {}
    return ((cfg.get("collection") or {}).get("topic_name")) or None


def candidates(conn, market_id: int, *, limit: int = LIMIT,
               redo: bool = False) -> List[Dict[str, Any]]:
    """Reviewed vendor posts the page could show that have no verdict yet."""
    rows = conn.execute(text("""
        SELECT a.uri, a.title, a.summary, a.news_source
          FROM bw_market_articles ma
          JOIN articles a ON a.uri = ma.article_uri
         WHERE ma.market_id = :m
           AND a.bias_source = 'vendor:linkedin'
           AND ma.review_verdict IN ('signal', 'commentary')
           AND (:redo OR NOT (COALESCE(ma.review_check, '{}'::jsonb) ? 'relevance'))
         ORDER BY COALESCE(a.publication_date, a.submission_date) DESC
         LIMIT :lim
    """), {"m": market_id, "lim": int(limit), "redo": bool(redo)}).mappings().all()
    return [dict(r) for r in rows]


def assess(conn, market: Dict[str, Any], *, limit: int = LIMIT,
           redo: bool = False) -> Dict[str, Any]:
    """Assess each unread post against the market topic and store the verdict.
    Synchronous (the scorer is), so the scheduler runs it in a thread."""
    from app.database import get_database_instance
    from app.services.automated_ingest_service import (
        AutomatedIngestService, relevance_evidence)
    from app.services.hybrid_relevance_service import RelevanceUnavailableError

    topic = market_topic(market)
    if not topic:
        return {"skipped": "market has no collection topic"}
    posts = candidates(conn, market["id"], limit=limit, redo=redo)
    conn.commit()
    result = {"topic": topic, "candidates": len(posts), "accepted": 0,
              "rejected": 0, "unavailable": 0}
    if not posts:
        return result

    svc = AutomatedIngestService(get_database_instance())
    threshold = svc.get_relevance_threshold(topic)
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg or "{}")
    keywords = list(cfg.get("collection_terms") or [])
    for post in posts:
        try:
            scored = svc.score_article_relevance(
                {"uri": post["uri"], "title": post["title"] or "",
                 "summary": post["summary"] or "", "news_source": post["news_source"]},
                topic, keywords, threshold=threshold)
        except RelevanceUnavailableError as exc:
            # Left unread: the next run asks again.
            result["unavailable"] += 1
            logger.warning("post relevance unavailable for %s: %s", post["uri"], exc)
            continue
        evidence = relevance_evidence(scored, threshold)
        verdict = {
            "accepted": bool(evidence["relevance_accepted_applied"]),
            "score": scored.get("topic_alignment_score"),
            "threshold": evidence["relevance_threshold_applied"],
            "engine": evidence["relevance_decision_engine"],
            "scores": evidence["relevance_engine_scores"],
            "policy": evidence["relevance_policy_version"],
            "topic": topic,
            "read_at": datetime.now(timezone.utc).isoformat(),
        }
        result["accepted" if verdict["accepted"] else "rejected"] += 1
        conn.execute(text("""
            UPDATE bw_market_articles
               SET review_check = COALESCE(review_check, '{}'::jsonb)
                                  || jsonb_build_object('relevance', CAST(:v AS JSONB))
             WHERE market_id = :m AND article_uri = :uri
        """), {"m": market["id"], "uri": post["uri"],
               "v": json.dumps(verdict, default=str)})
        conn.commit()
    return result


def passes(check: Optional[Dict[str, Any]]) -> bool:
    """Whether the post may be shown: unread, or accepted."""
    reading = (check or {}).get("relevance") if isinstance(check, dict) else None
    if not isinstance(reading, dict):
        return True
    return bool(reading.get("accepted"))


#: The same rule as SQL, for ``bw_market_articles`` aliased ``ma``.
PASSES_SQL = "COALESCE(ma.review_check->'relevance'->>'accepted', 'true') <> 'false'"
