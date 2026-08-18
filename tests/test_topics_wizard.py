"""Topics wizard correctness: edits must stick, overlays must be valid and whole.

Three problems, all of which let the wizard report success while the stored
state was wrong:

* Re-posting an existing topic returned the stored row untouched. An analyst who
  stepped back in the wizard and corrected the display name, description, owner,
  tags or source topics had those edits silently discarded.
* ``_TopicMetadataPatch`` had no ``source_topics`` field, so the corpus backing a
  tracked topic could be set only at creation and a wrong choice was
  uncorrectable through the API.
* The overlay was written straight to the production path with no structural
  check and no atomic write, so a malformed or half-written file could land
  where the deck builder and the scheduler read it.

Facade calls are stubbed; nothing here touches the database, and overlay writes
go to a temp directory.
"""

import asyncio
import json
from unittest.mock import Mock

import pytest

TOPIC = "Quantum Advantage"


def _install(monkeypatch, existing=None):
    import app.database as appdb

    facade = Mock()
    facade.get_forecast_topic_metadata.return_value = existing
    facade.upsert_forecast_topic_metadata.side_effect = (
        lambda topic, **kw: {"topic": topic, **kw}
    )
    db = Mock()
    db.facade = facade
    monkeypatch.setattr(appdb, "get_database_instance", lambda: db)
    return facade


# ── create / update semantics ───────────────────────────────────────────


def test_reposting_a_draft_applies_the_edited_metadata(monkeypatch):
    """The failure: going back in the wizard and fixing a field did nothing."""
    from app.routes.forecast_assessment_routes import (
        _TopicMetadataCreate, create_topic_metadata,
    )

    facade = _install(monkeypatch, existing={"topic": TOPIC, "status": "draft",
                                             "display_name": "old name"})

    payload = _TopicMetadataCreate(
        topic=TOPIC, display_name="corrected name", source_topics=["Quantum Computing"],
    )
    resp = asyncio.run(create_topic_metadata(payload))

    assert resp["created"] is False
    assert resp["updated"] is True
    kwargs = facade.upsert_forecast_topic_metadata.call_args.kwargs
    assert kwargs["display_name"] == "corrected name"
    assert kwargs["source_topics"] == ["Quantum Computing"]


def test_reposting_a_draft_with_nothing_new_does_not_write(monkeypatch):
    """A bare re-post stays idempotent rather than blanking stored fields."""
    from app.routes.forecast_assessment_routes import (
        _TopicMetadataCreate, create_topic_metadata,
    )

    facade = _install(monkeypatch, existing={"topic": TOPIC, "status": "draft"})

    resp = asyncio.run(create_topic_metadata(_TopicMetadataCreate(topic=TOPIC)))

    assert resp["updated"] is False
    facade.upsert_forecast_topic_metadata.assert_not_called()


def test_reposting_an_active_topic_is_rejected(monkeypatch):
    """Overwriting a live topic's metadata from a create call is not what the
    caller asked for; make them use PATCH."""
    from fastapi import HTTPException

    from app.routes.forecast_assessment_routes import (
        _TopicMetadataCreate, create_topic_metadata,
    )

    _install(monkeypatch, existing={"topic": TOPIC, "status": "active"})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_topic_metadata(
            _TopicMetadataCreate(topic=TOPIC, display_name="hijack")))

    assert exc.value.status_code == 409
    assert "PATCH" in exc.value.detail


def test_a_genuinely_new_topic_is_still_created(monkeypatch):
    from app.routes.forecast_assessment_routes import (
        _TopicMetadataCreate, create_topic_metadata,
    )

    _install(monkeypatch, existing=None)

    resp = asyncio.run(create_topic_metadata(_TopicMetadataCreate(topic=TOPIC)))

    assert resp["created"] is True


def test_patch_can_change_source_topics(monkeypatch):
    """Without this the corpus backing a topic was set once and uncorrectable."""
    from app.routes.forecast_assessment_routes import (
        _TopicMetadataPatch, patch_topic_metadata,
    )

    facade = _install(monkeypatch)

    asyncio.run(patch_topic_metadata(
        TOPIC, _TopicMetadataPatch(source_topics=["Quantum Computing", "Photonics"])))

    kwargs = facade.upsert_forecast_topic_metadata.call_args.kwargs
    assert kwargs["source_topics"] == ["Quantum Computing", "Photonics"]


# ── overlay validation ──────────────────────────────────────────────────


def _overlay(**kw):
    """The shape the five shipped overlays actually use."""
    base = {
        "topic": TOPIC,
        "deck_scenarios": {
            "fault_tolerance": {
                "deck_scenario_name": "Fault tolerance arrives",
                "horizon": "h2",
            },
        },
        "scenario_title_to_deck_key": {"Some stored title": "fault_tolerance"},
    }
    base.update(kw)
    return base


def test_a_valid_overlay_passes():
    from app.routes.forecast_assessment_routes import _validate_overlay

    assert _validate_overlay(_overlay(), TOPIC) == []


def test_every_shipped_overlay_still_validates():
    """The first version of this validator was written from a guessed schema
    and would have rejected all five production overlays. Check against the
    real files, not an invented shape."""
    import glob
    import json as _json

    from app.routes.forecast_assessment_routes import _validate_overlay

    files = sorted(glob.glob("data/wiley_horizons/*_deck_overlay.json"))
    assert files, "no overlays found — this check would pass vacuously"
    for path in files:
        overlay = _json.load(open(path))
        assert _validate_overlay(overlay, overlay.get("topic")) == [], path


@pytest.mark.parametrize("overlay,expected", [
    (_overlay(deck_scenarios={}), "non-empty"),
    (_overlay(deck_scenarios={"k": {"horizon": "h1"}}), "deck_scenario_name"),
    (_overlay(deck_scenarios={"k": {"deck_scenario_name": "n"}}), "horizon"),
    (_overlay(deck_scenarios={"k": {"deck_scenario_name": "n", "horizon": "h9"}}),
     "must be h1, h2, h3"),
])
def test_structurally_broken_overlays_are_caught(overlay, expected):
    """These degrade the deck builder silently rather than failing loudly, so
    they must be refused before the file is written."""
    from app.routes.forecast_assessment_routes import _validate_overlay

    problems = _validate_overlay(overlay, TOPIC)
    assert problems and any(expected in p for p in problems), problems


def test_spanning_horizons_are_accepted():
    """Three shipped overlays use h1_h2 / h2_h3 / h1_h3, and the deck builder
    treats a combined horizon as display-only rather than as an error."""
    from app.routes.forecast_assessment_routes import _validate_overlay

    for span in ("h1_h2", "h2_h3", "h1_h3"):
        overlay = _overlay(deck_scenarios={
            "k": {"deck_scenario_name": "n", "horizon": span}},
            scenario_title_to_deck_key={})
        assert _validate_overlay(overlay, TOPIC) == [], span


def test_a_title_map_pointing_at_a_missing_key_is_caught():
    """The map joins stored scenarios onto the deck; a dangling key renders
    nothing, silently."""
    from app.routes.forecast_assessment_routes import _validate_overlay

    overlay = _overlay(scenario_title_to_deck_key={"A title": "no_such_key"})
    problems = _validate_overlay(overlay, TOPIC)
    assert any("not in deck_scenarios" in p for p in problems), problems


def test_an_overlay_for_a_different_topic_is_caught():
    from app.routes.forecast_assessment_routes import _validate_overlay

    problems = _validate_overlay(_overlay(topic="Something Else"), TOPIC)
    assert any("topic" in p for p in problems)


# ── atomic write ────────────────────────────────────────────────────────


def test_overlay_is_written_atomically_and_leaves_no_temp_file(tmp_path, monkeypatch):
    """A crash or a concurrent reader must never see a half-written overlay."""
    from app.routes.forecast_assessment_routes import (
        _OverlayApprove, _overlay_slug, approve_topic_overlay,
    )
    import app.routes.forecast_assessment_routes as routes

    _install(monkeypatch)
    monkeypatch.setattr(routes, "_overlay_dir", lambda: tmp_path)

    resp = asyncio.run(approve_topic_overlay(
        TOPIC, _OverlayApprove(overlay=_overlay())))

    written = tmp_path / f"{_overlay_slug(TOPIC)}.json"
    assert written.exists()
    assert json.loads(written.read_text())["topic"] == TOPIC
    assert resp["overlay_path"] == str(written)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert not leftovers, f"temp files left behind: {leftovers}"


def test_a_broken_overlay_never_reaches_the_production_path(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from app.routes.forecast_assessment_routes import (
        _OverlayApprove, _overlay_slug, approve_topic_overlay,
    )
    import app.routes.forecast_assessment_routes as routes

    _install(monkeypatch)
    monkeypatch.setattr(routes, "_overlay_dir", lambda: tmp_path)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(approve_topic_overlay(
            TOPIC, _OverlayApprove(overlay=_overlay(deck_scenarios={}))))

    assert exc.value.status_code == 422
    assert not (tmp_path / f"{_overlay_slug(TOPIC)}.json").exists()
    assert not list(tmp_path.iterdir()), "a rejected overlay left files behind"
