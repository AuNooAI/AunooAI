"""Embedding repair sweep: approved news and relevant social posts.

docs/pipelines/08_INGEST_FIX_SPEC.md, WP5b (M5), and the social-post
embedding path. Vector search (Auspex, the MCP tools, similar articles)
only finds rows with an embedding. Until 7 Oct 2026 an encoder error during
ingest left an approved article without one for good, and social posts
were never embedded at all (2,041 of 2,229 relevant posts on bugfixing).

Who is eligible (``eligible_sql``):
- news: ``ingest_status = 'approved'``;
- social: ``ingest_status = 'social_evaluated'``, relevance at least 0.4,
  some usable text (title plus summary of ``SOCIAL_EMBED_MIN_CHARS``, 20),
  and not flagged as a false positive;
- both: readable by the central rule (no failed states, no copy of a
  readable original, no press release outside its topics). Rejected rows
  are never embedded here; a broader repair is a manual job.

Each pass takes up to ``EMBEDDING_REPAIR_BATCH`` (200) due rows, oldest due
first with the URI as tie-breaker, never repeats the analysis, and encodes
with ``EMBEDDING_REPAIR_CONCURRENCY`` (2) calls at a time. A per-row failure
counts an attempt and backs off; after ``EMBEDDING_MAX_ATTEMPTS`` (8) the row
waits for a person and shows as exhausted. When the encoder itself is
unreachable the pass stops without spending attempts: the rows stay overdue
and visible, and drain once it is back. A Postgres advisory lock keeps two
passes apart.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

_LOCK_KEY = 0x0E0C_2027


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def max_attempts() -> int:
    return _env_int("EMBEDDING_MAX_ATTEMPTS", 8)


def eligible_sql(ref: str = "articles") -> str:
    from app.services.article_visibility import RELEVANCE_FLOOR, readable_sql
    min_chars = _env_int("SOCIAL_EMBED_MIN_CHARS", 20)
    return (f"({ref}.embedding IS NULL AND {readable_sql(ref)} AND ("
            f"{ref}.ingest_status = 'approved' OR ("
            f"{ref}.ingest_status = 'social_evaluated' "
            f"AND {ref}.topic_alignment_score >= {RELEVANCE_FLOOR} "
            f"AND length(COALESCE({ref}.title, '') || COALESCE({ref}.summary, '')) >= {min_chars} "
            f"AND NOT EXISTS (SELECT 1 FROM bw_finding_reviews _fpr "
            f"WHERE _fpr.article_uri = {ref}.uri AND _fpr.status = 'false_positive'))))")


def _due_rows(conn, limit: int) -> List[Dict[str, Any]]:
    rows = conn.execute(text(f"""
        SELECT uri, title, summary, ingest_status, embedding_attempts
          FROM articles
         WHERE {eligible_sql()}
           AND COALESCE(embedding_attempts, 0) < :cap
           AND (embedding_next_retry_at IS NULL OR embedding_next_retry_at <= NOW())
         ORDER BY embedding_due_at ASC NULLS LAST, uri ASC
         LIMIT :limit
    """), {"cap": max_attempts(), "limit": int(limit)}).mappings().fetchall()
    return [dict(r) for r in rows]


class EncoderUnavailable(Exception):
    pass


def _encode(title: str, body: str):
    from app.vector_store_pgvector import _encode_fields
    try:
        return _encode_fields(title, body)
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__.lower()
        msg = str(exc).lower()
        if "connect" in name or "connection" in msg or "refused" in msg or "timed out" in msg \
                or "timeout" in name:
            raise EncoderUnavailable(f"{type(exc).__name__}: {exc}") from exc
        raise


def _store(conn, uri: str, vec) -> None:
    from app.vector_store_pgvector import _check_vector
    conn.execute(text("""
        UPDATE articles SET embedding = CAST(:e AS vector), embedding_attempts = NULL,
               embedding_last_error = NULL, embedding_next_retry_at = NULL
         WHERE uri = :u AND embedding IS NULL
    """), {"e": _check_vector(vec), "u": uri})
    conn.commit()


async def repair_once(db=None, *, batch: Optional[int] = None,
                      encode=None) -> Dict[str, Any]:
    """One pass. ``encode(title, body)`` exists for tests."""
    from app.database import get_database_instance
    from app.vector_store_pgvector import record_embedding_failure
    from app.tasks.embedding_backfill import _doc_text
    db = db or get_database_instance()
    batch = batch if batch is not None else _env_int("EMBEDDING_REPAIR_BATCH", 200)
    encode = encode or _encode
    out = {"selected": 0, "stored": 0, "failed": 0, "encoder_unavailable": False}

    lock_conn = await asyncio.to_thread(db._temp_get_connection)
    try:
        got = await asyncio.to_thread(
            lambda: lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}).scalar())
        if not got:
            out["skipped"] = "locked"
            return out
        rows = await asyncio.to_thread(_due_rows, lock_conn, batch)
        out["selected"] = len(rows)
        sem = asyncio.Semaphore(max(1, _env_int("EMBEDDING_REPAIR_CONCURRENCY", 2)))
        stop = asyncio.Event()

        async def one(row):
            if stop.is_set():
                return
            async with sem:
                if stop.is_set():
                    return
                title, body = _doc_text(row.get("title"), row.get("summary"))
                try:
                    vec = await asyncio.to_thread(encode, title, body)
                except EncoderUnavailable as exc:
                    stop.set()
                    out["encoder_unavailable"] = True
                    out["error"] = str(exc)[:300]
                    return
                except Exception as exc:  # noqa: BLE001 - this row's fault
                    out["failed"] += 1
                    await asyncio.to_thread(record_embedding_failure, row["uri"], f"{type(exc).__name__}: {exc}")
                    return
                conn = await asyncio.to_thread(db._temp_get_connection)
                try:
                    await asyncio.to_thread(_store, conn, row["uri"], vec)
                    out["stored"] += 1
                except Exception as exc:  # noqa: BLE001 - e.g. wrong width
                    out["failed"] += 1
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    await asyncio.to_thread(record_embedding_failure, row["uri"], f"{type(exc).__name__}: {exc}")
                finally:
                    conn.close()

        await asyncio.gather(*(one(r) for r in rows))
        return out
    finally:
        # The connection goes back to a pool, which does not end the session:
        # the lock must be released explicitly or every later pass is "locked".
        def _release():
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
                lock_conn.commit()
            finally:
                lock_conn.close()
        try:
            await asyncio.to_thread(_release)
        except Exception:  # noqa: BLE001
            pass


def health(db) -> Dict[str, Any]:
    """Check E and the all-age backlog. ``overdue`` is due more than an hour
    ago; ``legacy`` has no due time (approved before 7 Oct 2026), counted
    apart instead of being given an invented one."""
    conn = None
    try:
        conn = db._temp_get_connection()
        r = conn.execute(text(f"""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE embedding_due_at < NOW() - interval '1 hour'),
                   COUNT(*) FILTER (WHERE embedding_due_at > NOW() - interval '24 hours'),
                   COUNT(*) FILTER (WHERE embedding_due_at IS NULL),
                   COUNT(*) FILTER (WHERE COALESCE(embedding_attempts, 0) >= :cap),
                   COUNT(*) FILTER (WHERE ingest_status = 'social_evaluated'),
                   MIN(embedding_due_at),
                   MAX(embedding_last_error)
              FROM articles WHERE {eligible_sql()}
        """), {"cap": max_attempts()}).fetchone()
        return {"missing": int(r[0]), "overdue": int(r[1]), "due_last_24h": int(r[2]),
                "legacy_no_due_time": int(r[3]), "exhausted": int(r[4]), "social": int(r[5]),
                "oldest_due": r[6].isoformat() if r[6] else None, "a_last_error": r[7]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        if conn is not None:
            conn.close()


async def run_embedding_repair() -> None:
    """Background loop, every EMBEDDING_REPAIR_MINUTES (default 10). A pass
    that found a full batch runs again after a short pause."""
    from app.utils.shutdown import interruptible_sleep, is_shutting_down
    interval = max(1, _env_int("EMBEDDING_REPAIR_MINUTES", 10)) * 60
    logger.info("embedding repair sweep started (every %d min)", interval // 60)
    while not is_shutting_down():
        pause = interval
        try:
            out = await repair_once()
            if out.get("selected") or out.get("encoder_unavailable"):
                logger.info("embedding repair: %s", out)
            if out.get("stored") and out.get("selected", 0) >= _env_int("EMBEDDING_REPAIR_BATCH", 200):
                pause = 5
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("embedding repair pass failed: %s", exc, exc_info=True)
        if await interruptible_sleep(pause):
            break
    logger.info("embedding repair sweep stopped")
