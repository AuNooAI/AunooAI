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

#: Review kinds that are news about the company itself, not about a topic.
#: "Kevin Gandhi has joined Artemis as a security analyst" is not about AI in
#: the SOC and the assessment says so, but a hire, a round, a purchase or a
#: breach at a tracked vendor belongs on its market's page whatever the post
#: is about, and feeds the map. These are neither assessed nor hidden.
COMPANY_KINDS = ("funding", "acquisition", "hiring", "incident", "customer")
# Customer posts are in the list for a different reason: the customer-fit
# check already asks whether the deal is in the market, and the topic score
# turned away Nova Intelligence's ZEISS and Fresenius customers on panaya.


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
           AND LOWER(COALESCE(ma.review_kind, '')) <> ALL(:company)
           AND (:redo OR NOT (COALESCE(ma.review_check, '{}'::jsonb) ? 'relevance'))
         ORDER BY COALESCE(a.publication_date, a.submission_date) DESC
         LIMIT :lim
    """), {"m": market_id, "lim": int(limit), "redo": bool(redo),
           "company": list(COMPANY_KINDS)}).mappings().all()
    return [dict(r) for r in rows]


def assess(conn, market: Dict[str, Any], *, limit: int = LIMIT,
           redo: bool = False) -> Dict[str, Any]:
    """Assess each unread post against the market topic and store the verdict.
    Synchronous (the scorer is), so the scheduler runs it in a thread."""
    import inspect

    from app.database import get_database_instance
    from app.services import automated_ingest_service as ais
    try:
        from app.services.hybrid_relevance_service import RelevanceUnavailableError
    except ImportError:  # a site from before the ingest fix (oviva, panaya, sunstar)
        class RelevanceUnavailableError(Exception):
            pass

    topic = market_topic(market)
    if not topic:
        return {"skipped": "market has no collection topic"}
    cfg = market.get("config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg or "{}")
    # A market can opt out (config.post_relevance = false). Oviva's market
    # topic is the brand name with no scope text, so the score turned away
    # Oviva's own posts and Weight Watchers on GLP-1 cover (12 Oct 2026).
    if cfg.get("post_relevance") is False:
        return {"skipped": "post_relevance off for this market"}
    posts = candidates(conn, market["id"], limit=limit, redo=redo)
    conn.commit()
    result = {"topic": topic, "candidates": len(posts), "accepted": 0,
              "rejected": 0, "unavailable": 0}
    if not posts:
        return result

    svc = ais.AutomatedIngestService(get_database_instance())
    threshold = svc.get_relevance_threshold(topic)
    # Sites from before the ingest fix score without a threshold and record no
    # decision; there the decision is the one the site's readers apply.
    takes_threshold = "threshold" in inspect.signature(svc.score_article_relevance).parameters
    keywords = list(cfg.get("collection_terms") or [])
    for post in posts:
        try:
            article = {"uri": post["uri"], "title": post["title"] or "",
                       "summary": post["summary"] or "", "news_source": post["news_source"]}
            scored = (svc.score_article_relevance(article, topic, keywords, threshold=threshold)
                      if takes_threshold else
                      svc.score_article_relevance(article, topic, keywords))
        except RelevanceUnavailableError as exc:
            # Left unread: the next run asks again.
            result["unavailable"] += 1
            logger.warning("post relevance unavailable for %s: %s", post["uri"], exc)
            continue
        evidence = _evidence(ais, scored, threshold)
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


def _evidence(ais, scored: Dict[str, Any], threshold: float) -> Dict[str, Any]:
    """The decision as ingest records it, or the same fields worked out the
    way ``relevance_evidence`` does on a site that predates it."""
    if hasattr(ais, "relevance_evidence"):
        return ais.relevance_evidence(scored, threshold)
    try:
        from app.services.article_visibility import RELEVANCE_FLOOR
    except ImportError:
        RELEVANCE_FLOOR = 0.4
    floor = max(float(threshold or 0.0), float(RELEVANCE_FLOOR))
    score = float(scored.get("relevance_score") or scored.get("topic_alignment_score") or 0.0)
    accepted_by = scored.get("_accepted_by")
    return {
        "relevance_threshold_applied": floor,
        "relevance_accepted_applied": bool(accepted_by) or score >= floor,
        "relevance_decision_engine": str(accepted_by or scored.get("_hybrid_method") or "unknown")[:48],
        "relevance_engine_scores": scored.get("_engine_scores") or {},
        "relevance_policy_version": "pre-ingest-fix",
    }


def passes(check: Optional[Dict[str, Any]], kind: Optional[str] = None) -> bool:
    """Whether the post may be shown: company news, unread, or accepted."""
    if (kind or "").lower() in COMPANY_KINDS:
        return True
    reading = (check or {}).get("relevance") if isinstance(check, dict) else None
    if not isinstance(reading, dict):
        return True
    return bool(reading.get("accepted"))


#: The same rule as SQL, for ``bw_market_articles`` aliased ``ma``.
PASSES_SQL = ("(LOWER(COALESCE(ma.review_kind, '')) IN ("
              + ", ".join(f"'{k}'" for k in COMPANY_KINDS) + ")"
              " OR COALESCE(ma.review_check->'relevance'->>'accepted', 'true') <> 'false')")
