"""Answering review tasks, rather than clearing them.

The queue raised good questions — a headcount of zero, a growth figure with no
year to grow from — and offered one button, Resolve, which set a status and
changed nothing. So "resolved" meant "somebody looked at this", the underlying
value stayed wrong, and the queue taught the operator to empty it rather than
act on it.

Two things fix that. A task can be **answered** by writing the corrected value
into the registry, with the source recorded next to it. And a task can be
**auto-closed** when collection has since answered it on its own — ten of these
say a headcount is zero, and LinkedIn readings have since been collected.

The distinction between outcomes is deliberate. Fixing a wrong headcount,
accepting that a 2026 company cannot have a year-on-year figure, and dismissing
a flag that was mistaken are three different acts, and they used to be
indistinguishable.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

OUTCOMES = ("fixed", "accepted", "dismissed", "superseded")

# Where each answerable field lives inside bw_market_brands.baseline. A field
# absent here can still be accepted or dismissed; it just cannot be written to
# from the queue, which is better than writing it to a guessed path.
FIELD_PATHS: Dict[str, tuple] = {
    "employee_count": ("metrics", "employee_count"),
    "employee_growth_ytd": ("metrics", "employee_growth_ytd"),
    "total_funding_musd": ("funding_baseline", "total_musd"),
    "founded_year": ("founded_year",),
    "hq_country": ("hq_country",),
}

NUMERIC_FIELDS = {"employee_count", "employee_growth_ytd",
                  "total_funding_musd", "founded_year"}


def _coerce(field: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if field not in NUMERIC_FIELDS:
        return str(value).strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number, got {value!r}")
    return int(number) if number.is_integer() else number


def apply_fix(conn, market_id: int, task_id: int, *, value: Any,
              source: str, note: str = "") -> Dict[str, Any]:
    """Write a corrected value into the registry and close the task.

    The source is required, not optional. A corrected figure with no statement
    of where it came from is the same problem the task was raised about, moved
    one step later.
    """
    task = conn.execute(text("""
        SELECT id, brand_id, target_field, message
        FROM bw_review_tasks WHERE id = :i AND market_id = :m
    """), {"i": task_id, "m": market_id}).mappings().first()
    if not task:
        raise ValueError("task not found")
    field = task["target_field"]
    if not field:
        raise ValueError("this task is not about a single field, so it cannot "
                         "be fixed from here — accept or dismiss it instead")
    if field not in FIELD_PATHS:
        raise ValueError(f"no registry path known for {field}")
    if not task["brand_id"]:
        raise ValueError("this task names no vendor")
    if not (source or "").strip():
        raise ValueError("a source is required for a correction")

    coerced = _coerce(field, value)
    path = FIELD_PATHS[field]

    # jsonb_set needs the parent object to exist, and a baseline written by an
    # older import may not have one.
    if len(path) == 2:
        conn.execute(text("""
            UPDATE bw_market_brands
            SET baseline = jsonb_set(baseline, :parent,
                    COALESCE(baseline #> :parent, '{}'::jsonb), true)
            WHERE market_id = :m AND brand_id = :b
        """), {"m": market_id, "b": task["brand_id"],
               "parent": "{" + path[0] + "}"})

    conn.execute(text("""
        UPDATE bw_market_brands
        SET baseline = jsonb_set(baseline, :path, CAST(:val AS JSONB), true),
            updated_at = NOW()
        WHERE market_id = :m AND brand_id = :b
    """), {"m": market_id, "b": task["brand_id"],
           "path": "{" + ",".join(path) + "}",
           "val": json.dumps(coerced)})

    # The correction and its source are appended to the vendor's provenance,
    # so a value fixed by hand is as traceable as one that was imported.
    conn.execute(text("""
        UPDATE bw_market_brands
        SET baseline = jsonb_set(baseline, '{provenance}',
                COALESCE(baseline->'provenance', '[]'::jsonb)
                    || CAST(:entry AS JSONB), true)
        WHERE market_id = :m AND brand_id = :b
    """), {"m": market_id, "b": task["brand_id"],
           "entry": json.dumps([{
               "field": field, "value": coerced, "source": source.strip(),
               "note": note.strip() or None, "via": "review_task",
               "task_id": task_id}])})

    conn.execute(text("""
        UPDATE bw_review_tasks
        SET status = 'resolved', outcome = 'fixed',
            resolution = CAST(:res AS JSONB), resolved_at = NOW(),
            updated_at = NOW()
        WHERE id = :i
    """), {"i": task_id, "res": json.dumps({
        "field": field, "value": coerced, "source": source.strip(),
        "note": note.strip() or None})})
    conn.commit()
    return {"ok": True, "id": task_id, "field": field, "value": coerced,
            "outcome": "fixed"}


def close_task(conn, market_id: int, task_id: int, *, outcome: str,
               note: str = "") -> Dict[str, Any]:
    """Accept or dismiss a task without changing any data.

    ``accepted`` is for a question with no answer — a company founded in 2026
    cannot have a year-on-year growth figure, and no correction will make one
    exist. ``dismissed`` is for a flag that was wrong. Recording which is which
    is the point; both used to write the same row.
    """
    if outcome not in ("accepted", "dismissed"):
        raise ValueError(f"outcome must be accepted or dismissed, got {outcome}")
    updated = conn.execute(text("""
        UPDATE bw_review_tasks
        SET status = 'resolved', outcome = :o,
            resolution = CAST(:res AS JSONB), resolved_at = NOW(),
            updated_at = NOW()
        WHERE id = :i AND market_id = :m
    """), {"i": task_id, "m": market_id, "o": outcome,
           "res": json.dumps({"note": note.strip() or None})}).rowcount
    conn.commit()
    if not updated:
        raise ValueError("task not found")
    return {"ok": True, "id": task_id, "outcome": outcome}


def auto_close(conn, market_id: int, *, dry_run: bool = False) -> Dict[str, Any]:
    """Close tasks that collection has since answered.

    Only where the answer is unambiguous: the task complains a value is missing
    or zero, and a reading has since arrived for that exact field. A task about
    a *doubtful* value is left alone, because a second source agreeing with a
    figure nobody trusted is not the same as the doubt being resolved.
    """
    candidates = [dict(r) for r in conn.execute(text("""
        SELECT t.id, t.brand_id, t.target_field, t.message, b.display_name
        FROM bw_review_tasks t
        JOIN bw_brands b ON b.id = t.brand_id
        WHERE t.market_id = :m AND t.status = 'open'
          AND t.target_field IN ('employee_count', 'linkedin')
          AND (t.message LIKE 'Headcount recorded as zero%'
               OR t.message LIKE 'Missing field%'
               OR t.message LIKE '%has no LinkedIn company URL%')
    """), {"m": market_id}).mappings().all()]

    closed: List[Dict[str, Any]] = []
    for task in candidates:
        answer = None
        if task["target_field"] == "employee_count":
            answer = conn.execute(text("""
                SELECT (s.data->>'employee_count')::numeric
                FROM bw_vendor_snapshots s
                WHERE s.brand_id = :b AND s.snapshot_type = 'profile'
                  AND s.data->>'employee_count' IS NOT NULL
                  AND (s.data->>'employee_count')::numeric > 0
                ORDER BY s.observed_at DESC LIMIT 1
            """), {"b": task["brand_id"]}).scalar()
        elif task["target_field"] == "linkedin":
            answer = conn.execute(text("""
                SELECT i.normalized_value FROM bw_vendor_identifiers i
                WHERE i.brand_id = :b AND i.kind = 'linkedin_company_url'
                  AND i.valid_to IS NULL LIMIT 1
            """), {"b": task["brand_id"]}).scalar()
        if answer is None:
            continue

        closed.append({"id": task["id"], "vendor": task["display_name"],
                       "field": task["target_field"], "answer": str(answer)})
        if dry_run:
            continue
        conn.execute(text("""
            UPDATE bw_review_tasks
            SET status = 'resolved', outcome = 'superseded',
                resolution = CAST(:res AS JSONB),
                resolved_at = NOW(), auto_closed_at = NOW(), updated_at = NOW()
            WHERE id = :i
        """), {"i": task["id"], "res": json.dumps({
            "reason": "collection answered this",
            "field": task["target_field"], "observed": str(answer)})})

    if not dry_run and closed:
        conn.commit()
    return {"checked": len(candidates), "closed": len(closed),
            "dry_run": dry_run, "tasks": closed}
