"""Seed forecast_topic_metadata for topics that already exist.

Idempotent: existing rows are updated only when their derived overlay_status
or display_name has changed; status/description/owner/tags are left alone
once a human has filled them in.

Topics surfaced from any of:
  - forecast_topic_delivery (configured for delivery)
  - forecast_assessments    (mode='live' status='completed')
  - data/wiley_horizons/*_deck_overlay.json files

Run once per tenant after migration fa_006 has been applied.

Usage:
    ./.venv/bin/python scripts/backfill_topic_metadata.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

# Allow running directly from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_database_instance  # noqa: E402


logger = logging.getLogger("backfill_topic_metadata")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OVERLAY_DIR = Path(__file__).resolve().parent.parent / "data" / "wiley_horizons"


def _discover_overlay_topics() -> dict[str, str]:
    """Return {topic: overlay_filename} for every overlay JSON on disk."""
    out: dict[str, str] = {}
    if not OVERLAY_DIR.exists():
        return out
    for p in OVERLAY_DIR.glob("*_deck_overlay.json"):
        try:
            data = json.loads(p.read_text())
        except Exception as e:
            logger.warning("Skipping malformed overlay %s: %s", p.name, e)
            continue
        topic = data.get("topic")
        if topic:
            out[topic] = p.name
    return out


def _existing_topics(db) -> set[str]:
    """Union of every topic visible in the lifecycle view (delivery, assessment, metadata)."""
    return {r["topic"] for r in db.facade.list_topics_with_lifecycle() if r.get("topic")}


def main() -> int:
    db = get_database_instance()
    overlays = _discover_overlay_topics()
    logger.info("Found %d overlay files: %s", len(overlays), sorted(overlays.values()))

    topics = _existing_topics(db) | set(overlays.keys())
    if not topics:
        logger.info("No topics to backfill.")
        return 0

    seeded = 0
    updated = 0
    skipped = 0
    for topic in sorted(topics):
        # Derive overlay_status from disk presence. Hand-authored is the
        # default for pre-existing overlays; the wizard sets it to
        # auto_generated for new ones.
        derived_overlay = "human_reviewed" if topic in overlays else "missing"
        derived_display = topic if topic in overlays else None

        existing = db.facade.get_forecast_topic_metadata(topic)
        if not existing:
            db.facade.upsert_forecast_topic_metadata(
                topic,
                display_name=derived_display,
                status="active",
                overlay_status=derived_overlay,
            )
            seeded += 1
            logger.info("  seeded: %s (overlay=%s)", topic, derived_overlay)
            continue

        # Existing row: only fix overlay_status if it's wrong. Don't
        # clobber human-edited description/owner/tags/status.
        needs_update = False
        kwargs: dict[str, Optional[str]] = {}
        if existing.get("overlay_status") != derived_overlay:
            # If a human has already approved an overlay (human_reviewed),
            # don't downgrade just because the file moved.
            if derived_overlay == "human_reviewed" or existing.get("overlay_status") == "missing":
                kwargs["overlay_status"] = derived_overlay
                needs_update = True
        if needs_update:
            db.facade.upsert_forecast_topic_metadata(topic, **kwargs)
            updated += 1
            logger.info("  updated: %s (%s)", topic, kwargs)
        else:
            skipped += 1

    logger.info("Backfill done — seeded=%d updated=%d unchanged=%d total=%d",
                seeded, updated, skipped, len(topics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
