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


def _fetch_brand_retry_rows(db, limit: int) -> List[Dict[str, Any]]:
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
             WHERE m.relevance_status = 'relevance_check_failed' AND m.brand_relation IS NULL
               AND (g.topic LIKE 'Brand Monitoring %' OR g.topic LIKE '% - Brand Watch')
               AND COALESCE((m.last_failure->>'attempts')::int, 0) < :cap
             ORDER BY a.uri, a.submission_date DESC NULLS LAST
             LIMIT :limit
        """), {"cap": brand_retry_cap(), "limit": int(limit)}).mappings().fetchall()
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



def _article_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"uri": row.get("uri"), "url": row.get("uri"), "title": row.get("title") or "",
            "news_source": row.get("news_source") or "", "publication_date": row.get("publication_date"),
            "summary": row.get("summary") or "", "topic": row.get("topic"), "analyzed": False}


async def retry_brand_judgments(db, *, service=None, budget: int | None = None) -> Dict[str, Any]:
    budget = budget if budget is not None else _env_int("BRAND_RETRY_BUDGET", 25)
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, _fetch_brand_retry_rows, db, budget)
    out: Dict[str, Any] = {"selected": len(rows), "saved": 0, "decided_not_admitted": 0, "still_failed": 0,
                           "attempts_cap": brand_retry_cap(), "errors": [], "_service": service}
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
            res = await service.process_articles_batch(articles, topic, keywords or [], route="brand_retry")
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
