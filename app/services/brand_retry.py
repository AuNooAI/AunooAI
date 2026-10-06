"""Retry brand judgments that were unavailable.

docs/BRAND_RELEVANCE_SPEC.md: an unavailable model judgment stays visible and
retryable. Candidates whose brand judgment failed (match row
relevance_check_failed, no label) go back through the ingest pipeline, which
judges them again, under an attempt cap kept in last_failure and a per-call
budget. Called by the enrichment retry sweep where a site has it, and by
scripts/brand_retry.py (cron) where it does not. Does nothing with
BRAND_RELATION_DECISIONS off.

    BRAND_RETRY_BUDGET          rows per call, default 25
    BRAND_RETRY_MAX_ATTEMPTS    attempts per candidate, default 3
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def brand_retry_cap() -> int:
    return _env_int("BRAND_RETRY_MAX_ATTEMPTS", 3)


def _fetch_brand_retry_rows(db, limit: int, include_pending: bool = False) -> List[Dict[str, Any]]:
    """Brand-topic candidates whose brand judgment was unavailable, under the
    attempt cap, newest first. Only with BRAND_RELATION_DECISIONS on. Each
    row carries its brand topic, which may differ from the article's own."""
    try:
        from app.services.brand_decision import enabled
        if not enabled():
            return []
    except Exception:  # noqa: BLE001
        return []
    conn = None
    try:
        conn = db._temp_get_connection()
        rows = conn.execute(text("""
            SELECT DISTINCT ON (a.uri) a.uri, a.title, a.news_source, a.publication_date, a.summary,
                   g.topic, a.submission_date
              FROM keyword_article_matches m
              JOIN keyword_groups g ON g.id = m.group_id
              JOIN articles a ON a.uri = m.article_uri
             WHERE ((m.relevance_status = 'relevance_check_failed' AND m.brand_relation IS NULL)
                    OR (:pending AND m.relevance_status = 'pending' AND m.brand_relation IS NOT NULL
                        AND a.ingest_status = 'enrichment_failed'))
               AND (g.topic LIKE 'Brand Monitoring %' OR g.topic LIKE '% - Brand Watch')
               AND COALESCE((m.last_failure->>'attempts')::int, 0) < :cap
             ORDER BY a.uri, a.submission_date DESC NULLS LAST
             LIMIT :limit
        """), {"cap": brand_retry_cap(), "limit": int(limit), "pending": bool(include_pending)}).mappings().fetchall()
        if include_pending and rows:
            # An admitted item whose analysis failed keeps its label; nothing
            # else counts its retries, so each attempt is counted here, before
            # it runs, and the cap stops a permanently failing page.
            conn.execute(text("""
                UPDATE keyword_article_matches m
                   SET last_failure = jsonb_set(COALESCE(m.last_failure, '{}'::jsonb), '{attempts}',
                                                to_jsonb(COALESCE((m.last_failure->>'attempts')::int, 0) + 1))
                  FROM keyword_groups g
                 WHERE g.id = m.group_id AND m.article_uri = ANY(:uris)
                   AND m.relevance_status = 'pending' AND m.brand_relation IS NOT NULL
                   AND (g.topic LIKE 'Brand Monitoring %' OR g.topic LIKE '% - Brand Watch')
            """), {"uris": [r["uri"] for r in rows]})
            conn.commit()
        return sorted((dict(r) for r in rows), key=lambda r: r.get("submission_date") or "", reverse=True)
    except Exception as exc:  # noqa: BLE001 - columns absent before br_001
        logger.debug("enrichment retry sweep: brand retry query skipped: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass



def _retry_market_vendor_decisions(db, budget: int):
    """Market Monitor vendor decisions that were unavailable
    (docs/BRAND_RELEVANCE_MARKET_VENDORS.md); None with the flag off."""
    try:
        from app.services import market_vendor_decisions as mvd
        if not mvd.enabled():
            return None
    except Exception:  # noqa: BLE001
        return None
    conn = None
    try:
        conn = db._temp_get_connection()
        res = mvd.retry_unavailable(conn, budget)
        conn.commit()
        return res
    except Exception as exc:  # noqa: BLE001 - table absent before bm_001
        logger.warning("market vendor decision retry skipped: %s", exc)
        try:
            conn is not None and conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"error": str(exc)[:200]}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _article_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"uri": row.get("uri"), "url": row.get("uri"), "title": row.get("title") or "",
            "news_source": row.get("news_source") or "", "publication_date": row.get("publication_date"),
            "summary": row.get("summary") or "", "topic": row.get("topic"), "analyzed": False}


async def retry_brand_judgments(db, *, service=None, budget: int | None = None,
                                include_pending: bool = False) -> Dict[str, Any]:
    """include_pending: also retry admitted items whose analysis failed (match
    row 'pending', article enrichment_failed). Only the cron script asks for
    it: where the enrichment sweep exists, the sweep retries those already."""
    budget = budget if budget is not None else _env_int("BRAND_RETRY_BUDGET", 25)
    loop = asyncio.get_event_loop()
    market = await loop.run_in_executor(None, _retry_market_vendor_decisions, db, budget)
    rows = await loop.run_in_executor(None, _fetch_brand_retry_rows, db, budget, include_pending)
    out: Dict[str, Any] = {"selected": len(rows), "saved": 0, "decided_not_admitted": 0, "still_failed": 0,
                           "attempts_cap": brand_retry_cap(), "errors": [], "_service": service}
    if market is not None:
        out["market_vendor"] = market
    if not rows:
        return out
    if service is None:
        from app.services.automated_ingest_service import AutomatedIngestService
        service = AutomatedIngestService(db)
        out["_service"] = service
    by_topic: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_topic[r.get("topic")].append(_article_dict(r))
    for topic, articles in by_topic.items():
        try:
            keywords = await loop.run_in_executor(None, db.facade.get_monitored_keywords_for_topic, (topic,))
        except Exception:  # noqa: BLE001
            keywords = []
        try:
            # Only the newest ingest versions take a route label; older site
            # copies (sunstar, oviva, wiley-family on 6 Oct) do not.
            extra = {}
            try:
                import inspect
                if "route" in inspect.signature(service.process_articles_batch).parameters:
                    extra["route"] = "brand_retry"
            except (TypeError, ValueError):
                pass
            res = await service.process_articles_batch(articles, topic, keywords or [], **extra)
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"{topic}: {exc}")
            logger.error("brand retry for '%s' failed: %s", topic, exc)
            continue
        errs = res.get("errors") or []
        out["saved"] += int(res.get("saved") or 0)
        out["still_failed"] += len(errs)
        out["decided_not_admitted"] += max(0, int(res.get("processed") or 0) - int(res.get("saved") or 0) - len(errs))
        out["errors"].extend(str(e) for e in errs[:5])
    return out
