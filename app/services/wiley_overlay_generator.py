"""LLM-driven Wiley deck overlay generation.

Generates a proposed overlay JSON for a NEW topic by running the
``wiley_overlay_agent`` against the topic's Three Horizons run + most
recent live assessment, writing the result to
``data/wiley_horizons/{slug}_deck_overlay.json.proposed`` (NOT the
production file).

The wizard's "Overlay review" step (UI) reads the .proposed file, lets a
human edit it, and then calls
``POST /api/forecast/topics/{topic}/overlay/approve`` to persist the
final overlay.

Public surface:
- :func:`generate_overlay_proposal` — async, used by the route's
  background task.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


OVERLAY_DIR = Path(__file__).resolve().parents[2] / "data" / "wiley_horizons"


def _overlay_slug(topic: str) -> str:
    """Filesystem-safe slug, matches the existing hand-authored overlay names
    (`patent_cliffs_deck_overlay.json`, `us_federal_rd_deck_overlay.json`)."""
    s = re.sub(r"[^a-z0-9]+", "_", (topic or "").lower()).strip("_")
    return f"{s}_deck_overlay"


def _load_latest_run(db, topic: str) -> Optional[dict]:
    """Return the most recent Three Horizons run for this topic. Returns
    ``{id, raw_scenarios, model_used, created_at}`` or None."""
    from sqlalchemy import select
    try:
        from app.database_models import t_future_horizons_runs
    except Exception:
        logger.error("future_horizons_runs table not declared in models")
        return None

    stmt = (
        select(t_future_horizons_runs)
        .where(t_future_horizons_runs.c.topic == topic)
        .order_by(t_future_horizons_runs.c.created_at.desc())
        .limit(1)
    )
    row = db.facade._execute_with_rollback(stmt).fetchone()
    if not row:
        return None
    rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    raw = rd.get("raw_output") or {}
    # raw_output is JSON-encoded as either an object or already-parsed dict
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    scenarios = []
    # Common shapes in the wild: {"scenarios": [...]} or {"horizons": {h1:[...]}}
    if isinstance(raw, dict):
        if isinstance(raw.get("scenarios"), list):
            scenarios = raw["scenarios"]
        elif isinstance(raw.get("horizons"), dict):
            for horizon_key, items in raw["horizons"].items():
                for s in items or []:
                    if isinstance(s, dict):
                        s = {**s, "horizon": s.get("horizon") or horizon_key}
                        scenarios.append(s)
    return {
        "id": rd.get("id"),
        "raw_scenarios": scenarios,
        "model_used": rd.get("model_used"),
        "created_at": str(rd.get("created_at")),
    }


def _load_latest_assessment(db, topic: str) -> Optional[dict]:
    """Most recent live+completed assessment for this topic. Returns the
    facade-shaped dict (matches what the bundle uses), or None."""
    try:
        from app.database_models import t_forecast_assessments
        from sqlalchemy import select
    except Exception:
        return None

    stmt = (
        select(t_forecast_assessments)
        .where(t_forecast_assessments.c.topic == topic)
        .where(t_forecast_assessments.c.mode == "live")
        .where(t_forecast_assessments.c.status == "completed")
        .order_by(t_forecast_assessments.c.assessed_at.desc())
        .limit(1)
    )
    row = db.facade._execute_with_rollback(stmt).fetchone()
    if not row:
        return None
    return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)


def _build_agent_payload(topic: str, run: dict, assessment: Optional[dict]) -> dict:
    raw_scenarios = []
    for s in (run or {}).get("raw_scenarios", []) or []:
        if not isinstance(s, dict):
            continue
        raw_scenarios.append({
            "title": s.get("title") or s.get("scenario_title") or s.get("name") or "—",
            "horizon": s.get("horizon") or s.get("horizon_type") or "h1",
            "description": s.get("description") or s.get("synthesis") or "",
            "confidence": s.get("confidence"),
        })

    latest = None
    if assessment:
        # Map per-scenario verdict data the agent can use for consensus_pct
        # estimates and to surface concrete actors via supports/contradicts.
        summary = assessment.get("summary") or {}
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                summary = {}
        verdicts_brief = []
        for v in (summary.get("scenario_verdicts") or []) or []:
            if not isinstance(v, dict):
                continue
            verdicts_brief.append({
                "scenario_title": v.get("scenario_title") or v.get("title"),
                "supports": v.get("supports") or 0,
                "contradicts": v.get("contradicts") or 0,
                "current_consensus_pct": v.get("current_consensus_pct"),
            })
        latest = {
            "evidence_count": assessment.get("evidence_count"),
            "scenarios_count": assessment.get("scenarios_count"),
            "topic_briefing": (summary.get("topic_briefing") or {}) if isinstance(summary, dict) else {},
            "scenario_verdicts": verdicts_brief,
            "surprises": [
                {"label": s.get("label"), "size": s.get("size")}
                for s in (assessment.get("surprises") or []) if isinstance(s, dict)
            ],
        }

    return {
        "topic": topic,
        "run_id": (run or {}).get("id"),
        "raw_scenarios": raw_scenarios,
        "latest_assessment": latest,
    }


async def generate_overlay_proposal(
    topic: str, *, progress_callback=None,
) -> Tuple[Path, dict]:
    """Run the overlay agent and persist a .proposed file. Returns the
    proposed file path + the parsed overlay dict.

    Raises ``RuntimeError`` if no Three Horizons run exists for the topic
    (the wizard's step 2 must succeed before this can run).
    """
    from app.database import get_database_instance
    from app.services.wiley_bundle_supervisor import _call_agent

    def _emit(pct, msg):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    _emit(5, "Loading source Three Horizons run")
    db = get_database_instance()
    run = _load_latest_run(db, topic)
    if not run or not run.get("raw_scenarios"):
        raise RuntimeError(
            f"No Three Horizons run with scenarios found for topic '{topic}'. "
            "Run step 2 of the Add-Topic wizard first."
        )

    _emit(20, "Loading latest assessment (if any)")
    assessment = _load_latest_assessment(db, topic)

    payload = _build_agent_payload(topic, run, assessment)

    _emit(45, "Calling wiley_overlay_agent")
    overlay = await _call_agent("wiley_overlay_agent", payload, reasoning_effort="high")
    if not overlay or not overlay.get("deck_scenarios"):
        raise RuntimeError("Overlay agent returned no deck_scenarios.")

    # Ensure required identity fields are anchored to the input, not the
    # model's possibly-paraphrased echo
    overlay["topic"] = topic
    overlay.setdefault("source_run_id", run.get("id"))
    overlay.setdefault("description",
        f"Auto-generated overlay proposal for '{topic}'. Pending human review."
    )

    _emit(85, "Writing .proposed file")
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    proposed_path = OVERLAY_DIR / f"{_overlay_slug(topic)}.json.proposed"
    proposed_path.write_text(json.dumps(overlay, indent=2, ensure_ascii=False))

    # Mark the topic as auto_generated so the dashboard surfaces the
    # "Review overlay" CTA
    try:
        db.facade.upsert_forecast_topic_metadata(topic, overlay_status="auto_generated")
    except Exception as e:
        logger.warning("Failed to flip overlay_status for %s: %s", topic, e)

    _emit(100, "Overlay proposal saved")
    return proposed_path, overlay
