"""Background task: backfill DeBERTa (768d) embeddings for articles.

Part of the local-embeddings migration (docs/LOCAL_EMBEDDINGS_MIGRATION_PLAN.md).
The monolith previously embedded inline via OpenAI; that path stalled (only ~29%
of articles were ever embedded) and produced corrupt duplicates. After the
emb_001 migration drops articles.embedding to vector(768), this loop re-embeds
every article through the local DeBERTa encoder.

Newest-first by design: users query recent articles, so the freshest coverage
lights up first while the long tail fills in behind it.

Per-article errors are caught and skipped (the row stays NULL and is retried on
the next pass) — a single bad encode must not halt a 474k backfill. This differs
deliberately from the ingest write path (vector_store_pgvector._embed_texts),
which fails loud so a live ingest never silently stores a missing vector.
"""

import asyncio
import logging

from sqlalchemy import text

from app.database import get_database_instance
from app.vector_store_pgvector import _encode_one, _truncate_text_for_embedding

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
SLEEP_BETWEEN_BATCHES = 0.5   # work found — keep going, yield briefly
LOOP_INTERVAL = 600           # idle — re-check in 10 min for newly-ingested rows
INITIAL_DELAY = 60            # let the app finish booting

_status = {"running": False, "embedded_total": 0, "last_batch": 0, "last_error": None}


def get_task_status() -> dict:
    return dict(_status)


def _doc_text(title: str, summary: str) -> str:
    """Build the encoder input: title on line 1, summary as body (matches the
    title/body split in _encode_one)."""
    title = (title or "").strip()
    summary = (summary or "").strip()
    return f"{title}\n{summary}" if summary else title


def _process_batch() -> int:
    """Embed one batch of NULL-embedding articles (newest-first). Sync; returns
    the number embedded. Caller runs this in a thread."""
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text("""
            SELECT uri, title, summary
            FROM articles
            WHERE embedding IS NULL
              AND title IS NOT NULL AND title <> ''
            ORDER BY submission_date DESC
            LIMIT :batch
        """), {"batch": BATCH_SIZE}).fetchall()
        if not rows:
            return 0

        embedded = 0
        for uri, title, summary in rows:
            doc = _truncate_text_for_embedding(_doc_text(title, summary))
            if not doc.strip():
                continue
            try:
                vec = _encode_one(doc)
            except Exception as e:
                # Skip-and-retry: leave NULL, pick up next pass.
                _status["last_error"] = str(e)
                logger.warning("Backfill encode failed for %s: %s", uri, e)
                continue
            embedding_str = '[' + ','.join(str(x) for x in vec) + ']'
            conn.execute(
                text("UPDATE articles SET embedding = CAST(:e AS vector) WHERE uri = :u"),
                {"e": embedding_str, "u": uri},
            )
            embedded += 1
        conn.commit()
        return embedded
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def run_embedding_backfill() -> None:
    """Main loop: re-embed NULL-embedding articles, newest-first, until drained,
    then idle-poll for newly-ingested rows."""
    await asyncio.sleep(INITIAL_DELAY)
    _status["running"] = True
    logger.info("DeBERTa embedding backfill started")

    while True:
        try:
            count = await asyncio.to_thread(_process_batch)
            if count > 0:
                _status["embedded_total"] += count
                _status["last_batch"] = count
                logger.info(
                    "Embedding backfill: +%d (total %d this run)",
                    count, _status["embedded_total"],
                )
                await asyncio.sleep(SLEEP_BETWEEN_BATCHES)
                continue
        except asyncio.CancelledError:
            logger.info("Embedding backfill cancelled")
            _status["running"] = False
            return
        except Exception:
            logger.exception("Embedding backfill cycle failed")

        await asyncio.sleep(LOOP_INTERVAL)


async def backfill_embeddings(limit: int = 1000) -> int:
    """One-shot backfill for operator/admin use. Embeds up to ``limit`` articles
    (or until drained) and returns the count."""
    total = 0
    while total < limit:
        count = await asyncio.to_thread(_process_batch)
        if count == 0:
            break
        total += count
        await asyncio.sleep(SLEEP_BETWEEN_BATCHES)
    return total
