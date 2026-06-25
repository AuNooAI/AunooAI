"""Relabel surprise clusters in already-stored forecast assessments.

Runs ``forecast_cluster_label_agent`` over every assessment's
``surprises`` JSONB so users see human-readable cluster names + clean
sample-article lists without having to re-run paired assessments.

Idempotent on already-relabeled rows: clusters whose label is no longer
a keyword-salad pattern (commas + lowercase tokens) are left alone.

Usage:
    ./.venv/bin/python scripts/relabel_existing_clusters.py [--dry-run] [--topic 'Patent Cliffs']
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_database_instance  # noqa: E402

logger = logging.getLogger("relabel_clusters")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# Heuristic: keyword-salad labels are 2-5 lowercase comma-separated tokens.
# Real LLM names are Title Case with spaces. Tokens may contain hyphens
# ("h-net") and digits ("gpt-4"), so allow both inside each comma-separated
# token. Anchored to avoid matching arbitrary prose.
KEYWORD_SALAD_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*(?:,\s*[a-z0-9][a-z0-9\-]*){1,4}$")


def is_keyword_salad(label: str | None) -> bool:
    if not label:
        return False
    return bool(KEYWORD_SALAD_RE.match(label.strip()))


def _load_rows(db, topic_filter: str | None) -> list[dict]:
    from sqlalchemy import text as sa_text
    where = ""
    params = {}
    if topic_filter:
        where = "WHERE topic = :topic"
        params["topic"] = topic_filter
    sql = sa_text(f"""
        SELECT id, topic, surprises
        FROM forecast_assessments
        {where}
        ORDER BY assessed_at DESC
    """)
    rows = db.facade._execute_with_rollback(sql, params).fetchall()
    out = []
    for r in rows:
        rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        # surprises is JSONB — may come back as list or json-encoded string
        surp = rd.get("surprises")
        if isinstance(surp, str):
            try:
                surp = json.loads(surp)
            except Exception:
                surp = []
        rd["surprises"] = surp or []
        out.append(rd)
    return out


def _save_surprises(db, assessment_id: str, surprises: list) -> None:
    """Persist updated surprises JSONB back to the assessment row.

    Uses an explicit CAST :s AS jsonb so the python list is stored as a
    JSONB array (not a JSONB string) — same gotcha we already hit with the
    bundle review payload.
    """
    from sqlalchemy import text as sa_text
    sql = sa_text("""
        UPDATE forecast_assessments
        SET surprises = CAST(:surp AS jsonb)
        WHERE id = :id
    """)
    db.facade._execute_with_rollback(sql, {
        "surp": json.dumps(surprises),
        "id": assessment_id,
    })
    try:
        db.facade.session.commit()
    except Exception:
        pass


async def _relabel_one(topic: str, surprises: list) -> tuple[list, int, int]:
    """Run the LLM labeler on this assessment's clusters. Returns
    (new_surprises, n_renamed, n_dropped)."""
    from app.services.forecast_assessment_service import _label_clusters_with_llm

    # Only re-label clusters that still have a keyword-salad label —
    # leaves human-edited or already-relabeled ones alone.
    relabel_pool, passthrough = [], []
    for c in surprises:
        if is_keyword_salad(c.get("label")):
            relabel_pool.append(c)
        else:
            passthrough.append(c)

    if not relabel_pool:
        return surprises, 0, 0

    relabeled = await _label_clusters_with_llm(topic, relabel_pool)
    n_dropped = len(relabel_pool) - len(relabeled)
    n_renamed = sum(1 for c in relabeled if c.get("keyword_label"))
    return passthrough + relabeled, n_renamed, n_dropped


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    ap.add_argument("--topic", default=None, help="Only process assessments for this topic")
    args = ap.parse_args()

    db = get_database_instance()
    rows = _load_rows(db, args.topic)
    logger.info("Loaded %d assessment(s)%s", len(rows),
                f" for topic={args.topic!r}" if args.topic else "")

    total_renamed = total_dropped = total_touched = 0
    for r in rows:
        if not r["surprises"]:
            continue
        salad_clusters = [c for c in r["surprises"] if is_keyword_salad(c.get("label"))]
        if not salad_clusters:
            continue
        logger.info("  %s (%s): %d keyword-salad cluster(s)",
                    r["topic"], r["id"][:8], len(salad_clusters))
        try:
            new_surp, n_renamed, n_dropped = await _relabel_one(r["topic"], r["surprises"])
        except Exception as e:
            logger.error("    relabel failed: %s", e)
            continue
        for c in new_surp:
            if c.get("keyword_label"):
                logger.info("    '%s' -> '%s' (size %d)", c["keyword_label"], c["label"], c.get("size", 0))
        if args.dry_run:
            logger.info("    [dry-run] would persist %d cluster(s)", len(new_surp))
        else:
            _save_surprises(db, r["id"], new_surp)
            logger.info("    persisted")
        total_renamed += n_renamed
        total_dropped += n_dropped
        total_touched += 1

    logger.info("DONE — touched %d assessment(s), renamed=%d, dropped=%d", total_touched, total_renamed, total_dropped)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
