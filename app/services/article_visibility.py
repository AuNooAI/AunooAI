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

The rule (docs/pipelines/08_INGEST_FIX_SPEC.md, WP4, since 7 Oct 2026):

1. A row in a failed or pending ingest state (``FAILED_STATES``) is never
   readable, whatever its score. A failed relevance check stores NULL scores,
   and NULL alone would otherwise read as "never scored".
2. A row with a recorded decision (``relevance_accepted_applied`` not NULL)
   is readable when that decision accepted it. The decision was made against
   the deciding group's own threshold, or by an engine's own accept rule
   (Jev, cross-encoder, brand decision), and the row says which.
3. A legacy row with no recorded decision keeps the old score rule: readable
   when its topic alignment is at least ``relevance_threshold_applied``, else
   ``RELEVANCE_FLOOR`` (0.4). A row with no score is readable, because a
   missing score means the step never ran (manual submissions, rows older
   than the scorer), not that the article was judged off-topic.

Three forms of the same predicate, so no caller has to retype it:

- ``readable_clause(table)`` for SQLAlchemy Core selects on ``articles``
- ``readable_sql(alias)`` for hand-written SQL
- ``is_readable(row)`` for rows already in hand

Readers that must see everything (training, audit, the ingest pipeline itself)
say so explicitly with ``readable_only=False`` where a method offers it.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from sqlalchemy import and_, exists, or_, select

# Same floor as the Brand Watcher views, the social tab and the briefing
# composer. Since 7 Oct 2026 it applies only to legacy rows with no recorded
# decision and no recorded threshold.
RELEVANCE_FLOOR = 0.4

#: Ingest states that never reach a reader, whatever the score says.
FAILED_STATES = ("relevance_check_failed", "enrichment_failed", "quarantined_config",
                 "skipped_unknown_topic")

#: The decision rules readers apply, recorded by ingest with each decision.
POLICY_VERSION = "rel-2026-10-07"

# Since October 2026 two more facts decide readability, both recorded at
# ingest by app/services/story_identity.py:
#
# - A press release (source_type = 'press_release') is readable only in the
#   topics that show press releases (Market Monitoring by default).
# - A copy of a story (duplicate_of set) is hidden when its original is
#   readable. If the original was rejected or is a hidden press release, the
#   copy stays, so the story never vanishes because we picked the wrong copy.


def _pr_topics():
    from app.services.story_identity import press_release_topics
    return sorted(press_release_topics())


def _base_clause(table, pr_topics):
    from sqlalchemy import case, func, true
    score = table.c.topic_alignment_score
    accepted = table.c.relevance_accepted_applied
    legacy = or_(score.is_(None),
                 score >= func.coalesce(table.c.relevance_threshold_applied, RELEVANCE_FLOOR))
    return and_(
        or_(table.c.ingest_status.is_(None), table.c.ingest_status.notin_(FAILED_STATES)),
        case((accepted.is_not(None), accepted), else_=legacy) == true(),
        or_(table.c.source_type.is_distinct_from("press_release"),
            table.c.topic.in_(pr_topics)),
    )


def readable_clause(table):
    """SQLAlchemy condition for the ``articles`` table (or an alias of it)."""
    pr_topics = _pr_topics()
    # An alias of articles has the table as .element; alias the table itself.
    from sqlalchemy import Table
    base = table if isinstance(table, Table) else getattr(table, "element", table)
    original = base.alias("visibility_original")
    original_readable = exists(
        select(original.c.uri).where(
            original.c.uri == table.c.duplicate_of,
            _base_clause(original, pr_topics),
        )
    )
    return and_(
        _base_clause(table, pr_topics),
        or_(table.c.duplicate_of.is_(None), ~original_readable),
    )


def _base_sql(ref: str, pr_topics) -> str:
    score = f"{ref}.topic_alignment_score"
    topics = ", ".join("'" + t.replace("'", "''") + "'" for t in pr_topics)
    pr = (f"{ref}.source_type IS DISTINCT FROM 'press_release'"
          + (f" OR {ref}.topic IN ({topics})" if topics else ""))
    failed = ", ".join(f"'{st}'" for st in FAILED_STATES)
    status = f"({ref}.ingest_status IS NULL OR {ref}.ingest_status NOT IN ({failed}))"
    decided = (f"(CASE WHEN {ref}.relevance_accepted_applied IS NOT NULL "
               f"THEN {ref}.relevance_accepted_applied "
               f"ELSE ({score} IS NULL OR {score} >= COALESCE({ref}.relevance_threshold_applied, "
               f"{RELEVANCE_FLOOR})) END)")
    return f"({status} AND {decided} AND ({pr}))"


def readable_sql(alias: Optional[str] = None) -> str:
    """The predicate as SQL text, e.g. ``readable_sql('a')``. No alias for a bare table."""
    ref = alias or "articles"
    pr_topics = _pr_topics()
    return (f"({_base_sql(ref, pr_topics)} AND ({ref}.duplicate_of IS NULL OR NOT EXISTS ("
            f"SELECT 1 FROM articles visibility_original "
            f"WHERE visibility_original.uri = {ref}.duplicate_of "
            f"AND {_base_sql('visibility_original', pr_topics)})))")


def is_readable(row: Mapping[str, Any]) -> bool:
    """Python-side check on a row or result dict, same rule as the SQL when
    the row carries ingest_status and the decision columns. A row missing
    them is judged on what it has. Missing or unscored passes.

    A row in hand cannot show whether its original is readable, so a copy
    (``duplicate_of`` set) counts as unreadable here. Readers that need the
    exact rule should filter in SQL.
    """
    if not isinstance(row, Mapping):
        return True
    if row.get("duplicate_of"):
        return False
    if row.get("source_type") == "press_release" and \
            (row.get("topic") or "") not in set(_pr_topics()):
        return False
    if row.get("ingest_status") in FAILED_STATES:
        return False
    accepted = row.get("relevance_accepted_applied")
    if accepted is not None:
        return bool(accepted)
    v = row.get("topic_alignment_score")
    if v is None or isinstance(v, bool):
        return True
    floor = row.get("relevance_threshold_applied")
    try:
        floor = float(floor) if floor is not None else RELEVANCE_FLOOR
    except (TypeError, ValueError):
        floor = RELEVANCE_FLOOR
    try:
        return float(v) >= floor
    except (TypeError, ValueError):
        return True


# --- Copies and press releases only ------------------------------------------
#
# The news feed, the Explore analysis sample and the category lists never used
# the relevance floor above; they have their own rules. They still should not
# show a story twice or a press release in a topic that does not take them, so
# they apply this narrower filter instead of readable_clause.


def story_clause(table):
    """Hide press releases outside opted-in topics, and copies whose original is readable."""
    pr_topics = _pr_topics()
    from sqlalchemy import Table
    base = table if isinstance(table, Table) else getattr(table, "element", table)
    original = base.alias("story_original")
    original_readable = exists(
        select(original.c.uri).where(
            original.c.uri == table.c.duplicate_of,
            _base_clause(original, pr_topics),
        )
    )
    return and_(
        or_(table.c.source_type.is_distinct_from("press_release"),
            table.c.topic.in_(pr_topics)),
        or_(table.c.duplicate_of.is_(None), ~original_readable),
    )


def story_sql(alias: Optional[str] = None) -> str:
    """``story_clause`` as SQL text."""
    ref = alias or "articles"
    pr_topics = _pr_topics()
    topics = ", ".join("'" + t.replace("'", "''") + "'" for t in pr_topics)
    pr = (f"{ref}.source_type IS DISTINCT FROM 'press_release'"
          + (f" OR {ref}.topic IN ({topics})" if topics else ""))
    return (f"(({pr}) AND ({ref}.duplicate_of IS NULL OR NOT EXISTS ("
            f"SELECT 1 FROM articles story_original "
            f"WHERE story_original.uri = {ref}.duplicate_of "
            f"AND {_base_sql('story_original', pr_topics)})))")


# --- Evidence for the observer and signal agents ------------------------------
#
# The agents read analysed news (a category) and social posts, which the
# social evaluator scores but never categorises. A post counts when it is a
# real social row (social_meta set and not JSON null), scored at least
# RELEVANCE_FLOOR, and not flagged as a false positive. No category is
# invented for it. Pair this with readable_sql(), which handles failed
# states and copies.


def agent_evidence_sql(ref: str = "articles") -> str:
    return (f"({ref}.category IS NOT NULL OR ({ref}.social_meta IS NOT NULL "
            f"AND {ref}.social_meta::text <> 'null' "
            f"AND {ref}.topic_alignment_score >= {RELEVANCE_FLOOR} "
            f"AND NOT EXISTS (SELECT 1 FROM bw_finding_reviews _fpr "
            f"WHERE _fpr.article_uri = {ref}.uri AND _fpr.status = 'false_positive')))")
