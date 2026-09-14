"""One rule for "is this article row readable?", shared by every reader.

Quality control on this platform records a decision instead of enforcing one:
the ingest step scores every collected article for topic alignment and keeps
the rejects (``ingest_status = 'filtered_relevance'``) as labelled data for
retraining, and the Brand Watcher false-positive flags work the same way. The
store therefore holds what quality control threw out, and every reader has to
leave it out again.

Until 14 September 2026 each reader carried its own copy of that rule or none:
the Brand Watcher and dashboard routes filtered, the daily briefing composer
filtered, and Auspex chat, deep research, the Auspex tools service and the
MCP tools did not. An assistant reading a brand topic through MCP got 389
articles the dashboard showed none of (oviva, "Brand Monitoring Second
Nature").

The rule is the one the views use: an article is readable when its topic
alignment is at least ``RELEVANCE_FLOOR``. A row with no score is readable,
because a missing score means the step never ran (manual submissions, rows
older than the scorer), not that the article was judged off-topic.

Three forms of the same predicate, so no caller has to retype it:

- ``readable_clause(table)`` for SQLAlchemy Core selects on ``articles``
- ``readable_sql(alias)`` for hand-written SQL
- ``is_readable(row)`` for rows already in hand

Readers that must see everything (training, audit, the ingest pipeline itself)
say so explicitly with ``readable_only=False`` where a method offers it.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from sqlalchemy import or_

# Same floor as the Brand Watcher views, the social tab and the briefing composer.
RELEVANCE_FLOOR = 0.4


def readable_clause(table):
    """SQLAlchemy condition for the ``articles`` table (or an alias of it)."""
    col = table.c.topic_alignment_score
    return or_(col.is_(None), col >= RELEVANCE_FLOOR)


def readable_sql(alias: Optional[str] = None) -> str:
    """The predicate as SQL text, e.g. ``readable_sql('a')``. No alias for a bare table."""
    col = f"{alias}.topic_alignment_score" if alias else "topic_alignment_score"
    return f"({col} IS NULL OR {col} >= {RELEVANCE_FLOOR})"


def is_readable(row: Mapping[str, Any]) -> bool:
    """Python-side check on a row or result dict. Missing or unscored passes."""
    if not isinstance(row, Mapping):
        return True
    v = row.get("topic_alignment_score")
    if v is None or isinstance(v, bool):
        return True
    try:
        return float(v) >= RELEVANCE_FLOOR
    except (TypeError, ValueError):
        return True
