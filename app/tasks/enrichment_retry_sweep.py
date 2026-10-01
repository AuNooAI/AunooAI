"""Retry sweep for articles whose enrichment was blocked or failed.

Two kinds of row wait here (spec work package 22):

- ``quarantined_config``: the topic's configuration, not the article, stopped
  the analysis (an empty categories or future-signals list). These are
  retried only once the configuration block is gone, with no attempt cap,
  because retrying before that would fail the same way.
- ``enrichment_failed``: the article itself failed (no text, a model error).
  These are retried up to ``ENRICHMENT_MAX_ATTEMPTS`` times (default 3) and
  then left with their last error.

The sweep runs on a timer, newest rows first, under a per-tick budget, and
writes one run record per tick with provider ``enrichment_retry``.

Environment:
    ENRICHMENT_RETRY_SWEEP_ENABLED  "1" (default) starts the loop at boot
    ENRICHMENT_RETRY_SWEEP_MINUTES  minutes between ticks, default 30
    ENRICHMENT_RETRY_BUDGET         rows per tick, default 50
    ENRICHMENT_MAX_ATTEMPTS         cap for article faults, default 3
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.collectors.contracts import CollectionResult

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = ("quarantined_config", "enrichment_failed")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def max_attempts() -> int:
    return _env_int("ENRICHMENT_MAX_ATTEMPTS", 3)


def should_retry(row: Dict[str, Any], *, block_reason_now: Optional[str],
                 attempts_cap: Optional[int] = None) -> bool:
    """Whether one waiting row should be re-run this tick.

    ``block_reason_now`` is what ``configuration_block_reason`` says about
    the row's topic right now (None when the topic is fine). A
    quarantined_config row retries only when that is None. An
    enrichment_failed row retries while its attempt count is under the cap,
    and never while its topic is blocked, because the analysis would be
    refused before it started.
    """
    cap = attempts_cap if attempts_cap is not None else max_attempts()
    status = row.get("ingest_status")
    if block_reason_now:
        return False
    if status == "quarantined_config":
        return True
    if status == "enrichment_failed":
        return int(row.get("enrichment_attempts") or 0) < cap
    return False


def topic_configs() -> Dict[str, Dict[str, Any]]:
    """name -> topic config from config.json, read fresh each tick so a list
    filled in the UI is seen without a restart."""
    from app.config.config import load_config
    out: Dict[str, Dict[str, Any]] = {}
    try:
        for t in (load_config().get("topics") or []):
            if isinstance(t, dict) and t.get("name"):
                out[t["name"]] = t
    except Exception as exc:  # noqa: BLE001
        logger.warning("enrichment retry sweep: topic configuration not readable: %s", exc)
    return out


def block_reasons_for(topics, configs: Dict[str, Dict[str, Any]]) -> Dict[str, Optional[str]]:
    from app.services.automated_ingest_service import configuration_block_reason
    reasons: Dict[str, Optional[str]] = {}
    for t in topics:
        cfg = configs.get(t)
        reasons[t] = configuration_block_reason(cfg) if cfg is not None else f"topic '{t}': not in configuration"
    return reasons


def _fetch_waiting_rows(db, limit: int) -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = db._temp_get_connection()
        rows = conn.execute(text("""
            SELECT uri, title, news_source, publication_date, summary, topic,
                   ingest_status, enrichment_attempts, enrichment_block_reason, submission_date
              FROM articles
             WHERE ingest_status IN ('quarantined_config', 'enrichment_failed')
             ORDER BY submission_date DESC NULLS LAST
             LIMIT :limit
        """), {"limit": int(limit)}).mappings().fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("enrichment retry sweep: candidate query failed: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def select_candidates(rows: List[Dict[str, Any]], configs: Dict[str, Dict[str, Any]],
                      budget: int, attempts_cap: Optional[int] = None):
    """(selected, deferred_count, reasons). Rows are already newest first."""
    reasons = block_reasons_for({r.get("topic") for r in rows if r.get("topic")}, configs)
    selected: List[Dict[str, Any]] = []
    deferred = 0
    for r in rows:
        if len(selected) >= budget:
            deferred += 1
            continue
        if should_retry(r, block_reason_now=reasons.get(r.get("topic")), attempts_cap=attempts_cap):
            selected.append(r)
        else:
            deferred += 1
    return selected, deferred, reasons


def _article_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "uri": row.get("uri"),
        "url": row.get("uri"),
        "title": row.get("title") or "",
        "news_source": row.get("news_source") or "",
        "publication_date": row.get("publication_date"),
        "summary": row.get("summary") or "",
        "topic": row.get("topic"),
        "analyzed": False,
    }


async def sweep_once(db, *, budget: Optional[int] = None, service=None,
                     configs: Optional[Dict[str, Dict[str, Any]]] = None,
                     record: bool = True) -> Dict[str, Any]:
    """One tick. Returns the counts it recorded.

    ``service`` and ``configs`` exist so tests can pass fakes; production
    passes neither.
    """
    budget = budget if budget is not None else _env_int("ENRICHMENT_RETRY_BUDGET", 50)
    configs = configs if configs is not None else topic_configs()
    result = CollectionResult.ok([], provider="enrichment_retry", scope="sweep")
    result.mark_started()

    loop = asyncio.get_event_loop()
    # Read more than the budget so rows that cannot retry yet do not starve
    # the ones that can.
    rows = await loop.run_in_executor(None, _fetch_waiting_rows, db, max(budget * 4, 50))
    selected, deferred, reasons = select_candidates(rows, configs, budget)
    result.counts.add(received=len(rows), deferred=deferred)

    blocked_topics = sorted(t for t, r in reasons.items() if r)
    if blocked_topics:
        result.diagnostics["blocked_topics"] = {t: reasons[t] for t in blocked_topics}

    enriched = quarantined = failed = already_rejected = 0
    errors: List[str] = []
    if selected:
        if service is None:
            from app.services.automated_ingest_service import AutomatedIngestService
            service = AutomatedIngestService(db)
        by_topic: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in selected:
            by_topic[r.get("topic")].append(_article_dict(r))
        for topic, articles in by_topic.items():
            try:
                keywords = await loop.run_in_executor(
                    None, db.facade.get_monitored_keywords_for_topic, (topic,))
            except Exception:  # noqa: BLE001
                keywords = []
            try:
                out = await service.process_articles_batch(
                    articles, topic, keywords or [], route="enrichment_retry")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{topic}: {exc}")
                logger.error("enrichment retry sweep: batch for topic '%s' failed: %s", topic, exc)
                continue
            enriched += int(out.get("saved") or 0)
            quarantined += int(out.get("configuration_blocked") or 0)
            already_rejected += int(out.get("already_rejected") or 0)
            failed += len(out.get("errors") or [])
            errors.extend(str(e) for e in (out.get("errors") or [])[:5])

    # Rows that went through the batch and came out neither enriched nor
    # quarantined failed again for an article fault (no usable text, model
    # error). The batch reports those as filtered, not as errors, so count
    # them here or a tick that fixed nothing reads as "0 failed".
    still_failed = max(0, len(selected) - enriched - quarantined - already_rejected)
    result.counts.add(inserted=enriched, quarantined=quarantined, already_rejected=already_rejected,
                      invalid=still_failed)
    result.diagnostics.update({
        "selected": len(selected),
        "enriched": enriched,
        "quarantined": quarantined,
        "failed": failed,
        "still_failed": still_failed,
        "budget": budget,
    })
    if errors:
        result.diagnostics["errors"] = errors[:10]
    result.mark_finished()

    summary = {
        "received": len(rows),
        "selected": len(selected),
        "deferred": deferred,
        "enriched": enriched,
        "quarantined": quarantined,
        "failed": failed,
        "still_failed": still_failed,
        "blocked_topics": blocked_topics,
    }
    if record:
        try:
            from app.services.collection_runs import record_run
            summary["run_id"] = await loop.run_in_executor(
                None, lambda: record_run(db, result, scope_kind="sweep", scope_id="enrichment_retry"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("enrichment retry sweep: run record not written: %s", exc)
    logger.info("enrichment retry sweep: %s", summary)
    return summary


def health_counts(db) -> Dict[str, int]:
    """topic -> number of articles waiting on a configuration fix. For the
    health probe and the UI flag on the topic."""
    conn = None
    try:
        conn = db._temp_get_connection()
        rows = conn.execute(text("""
            SELECT COALESCE(topic, '') AS topic, COUNT(*) AS n
              FROM articles
             WHERE ingest_status = 'quarantined_config'
             GROUP BY topic
        """)).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("enrichment retry sweep: health counts failed: %s", exc)
        return {}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


async def run_enrichment_retry_sweep():
    """Background loop. Started by app_factory when
    ENRICHMENT_RETRY_SWEEP_ENABLED is not "0"."""
    from app.database import get_database_instance
    from app.utils.shutdown import interruptible_sleep, is_shutting_down

    interval = max(1, _env_int("ENRICHMENT_RETRY_SWEEP_MINUTES", 30)) * 60
    logger.info("enrichment retry sweep started (every %d min, budget %d, max attempts %d)",
                interval // 60, _env_int("ENRICHMENT_RETRY_BUDGET", 50), max_attempts())
    # First tick after one interval: boot is busy enough.
    while not is_shutting_down():
        if await interruptible_sleep(interval):
            break
        try:
            await sweep_once(get_database_instance())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("enrichment retry sweep tick failed: %s", exc, exc_info=True)
    logger.info("enrichment retry sweep stopped")
