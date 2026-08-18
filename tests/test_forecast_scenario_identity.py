"""Scenarios must be identified by a stable key, not by list position.

A verdict's ``scenario_idx`` is only its place in the list ``assess_run``
builds — a run's original scenarios followed by any promoted ones. That position
moves when a promoted scenario is added or skipped, and it means different
things in different runs, so it cannot be what status and verdicts hang off.

Two failures came from that:

* Promoted scenarios had no recorded identity, so the UI inferred the pairing by
  arithmetic — the i-th addendum was assumed to be the (N-K+i)-th verdict. Any
  addendum added between assessments, or skipped because it was marked done,
  shifted every pairing after it, showing one scenario's verdict under another's
  title and writing "mark done" to the wrong scenario.
* Original scenarios were keyed by index, so a reordered payload moved status
  onto a different scenario.

Migration fa_012 adds ``scenario_key`` and ``user_scenario_id`` and replaces the
scenario-status unique constraint, which could never fire under Postgres NULL
semantics, with a CHECK plus partial unique indexes.

No database here: the facade is exercised with a stubbed executor and the schema
contract is read off the SQLAlchemy metadata. See tests/conftest.py for why
tests in this repo must not touch live state.
"""

from unittest.mock import Mock

import pytest

RUN = "run-aaaa"


# ── Key derivation ──────────────────────────────────────────────────────


def test_key_is_stable_for_the_same_scenario():
    """The same stored scenario derives the same key every read, which is what
    lets a legacy run be keyed without rewriting its raw_output."""
    from app.services.scenario_identity import derive_scenario_key

    sc = {"type": "h2", "title": "Fault-tolerant qubits reach 1000"}
    assert derive_scenario_key(RUN, sc, 3) == derive_scenario_key(RUN, sc, 3)


def test_key_survives_cosmetic_title_edits():
    """Spacing and punctuation drift between runs must not re-identify it."""
    from app.services.scenario_identity import derive_scenario_key

    a = {"type": "h2", "title": "Fault-tolerant qubits reach 1,000"}
    b = {"type": "h2", "title": "  Fault tolerant   qubits reach 1000  "}
    assert derive_scenario_key(RUN, a, 3) == derive_scenario_key(RUN, b, 3)


def test_key_distinguishes_scenarios_that_share_a_title():
    """Decks repeat a heading across horizons; those must not collapse onto one
    key and share status."""
    from app.services.scenario_identity import derive_scenario_key

    sc = {"type": "h1", "title": "Adoption accelerates"}
    assert derive_scenario_key(RUN, sc, 0) != derive_scenario_key(RUN, sc, 1)
    assert derive_scenario_key(RUN, sc, 0) != derive_scenario_key(
        RUN, {"type": "h3", "title": "Adoption accelerates"}, 0)


def test_key_is_run_scoped():
    """A scenario of one run must never share identity with another run's."""
    from app.services.scenario_identity import derive_scenario_key

    sc = {"type": "h1", "title": "Adoption accelerates"}
    assert derive_scenario_key("run-a", sc, 0) != derive_scenario_key("run-b", sc, 0)


def test_stamped_key_wins_over_derivation():
    """Once a run is stamped, that key is the identity — deriving instead would
    silently re-point every row that already references it."""
    from app.services.scenario_identity import scenario_key_for

    sc = {"type": "h1", "title": "Adoption accelerates", "scenario_key": "stamped-123"}
    assert scenario_key_for(RUN, sc, 0) == "stamped-123"


def test_new_runs_get_keys_stamped_in():
    from app.services.scenario_identity import ensure_scenario_keys

    scenarios = [{"type": "h1", "title": "One"}, {"type": "h2", "title": "Two"}]
    ensure_scenario_keys(RUN, scenarios)

    keys = [s["scenario_key"] for s in scenarios]
    assert all(keys) and len(set(keys)) == 2


def test_stamping_twice_does_not_change_keys():
    """Re-persisting a run must not re-identify its scenarios."""
    from app.services.scenario_identity import ensure_scenario_keys

    scenarios = [{"type": "h1", "title": "One"}]
    ensure_scenario_keys(RUN, scenarios)
    first = scenarios[0]["scenario_key"]
    ensure_scenario_keys(RUN, scenarios)
    assert scenarios[0]["scenario_key"] == first


def test_reordering_scenarios_keeps_each_key_attached():
    """Acceptance criterion 11: status follows the scenario, not the slot."""
    from app.services.scenario_identity import index_scenarios_by_key

    scenarios = [
        {"type": "h1", "title": "One", "scenario_key": "k-one"},
        {"type": "h2", "title": "Two", "scenario_key": "k-two"},
        {"type": "h3", "title": "Three", "scenario_key": "k-three"},
    ]
    before = index_scenarios_by_key(RUN, scenarios)
    reordered = [scenarios[2], scenarios[0], scenarios[1]]
    after = index_scenarios_by_key(RUN, reordered)

    assert set(before) == set(after)
    for key in before:
        assert before[key][1]["title"] == after[key][1]["title"]
    # ...and the positions genuinely moved, so this is not a vacuous check.
    assert before["k-three"][0] != after["k-three"][0]


# ── Verdict persistence ─────────────────────────────────────────────────


def _facade_with_captured_insert():
    from app.database_query_facade import DatabaseQueryFacade

    facade = DatabaseQueryFacade.__new__(DatabaseQueryFacade)
    facade.logger = Mock()
    captured = {}

    def _exec(stmt, payload=None):
        captured["stmt"] = stmt
        captured["payload"] = payload
        return Mock()

    facade._execute_with_rollback = _exec
    return facade, captured


def _verdict_row(scenario_idx, user_scenario_id=None, scenario_key=None):
    return {
        "scenario_idx": scenario_idx,
        "horizon_type": "h1",
        "scenario_title": f"Scenario {scenario_idx}",
        "verdict_label": "On track",
        "user_scenario_id": user_scenario_id,
        "scenario_key": scenario_key,
    }


def test_verdicts_persist_the_identity_of_what_they_scored():
    facade, captured = _facade_with_captured_insert()

    ok = facade.save_forecast_scenario_verdicts("assess-1", [
        _verdict_row(0, scenario_key="k-one"),
        _verdict_row(1, scenario_key="k-two"),
        _verdict_row(2, user_scenario_id="promoted-aaa"),
        _verdict_row(3, user_scenario_id="promoted-bbb"),
    ])

    assert ok
    by_idx = {p["scenario_idx"]: p for p in captured["payload"]}
    assert by_idx[0]["scenario_key"] == "k-one"
    assert by_idx[1]["scenario_key"] == "k-two"
    assert by_idx[2]["user_scenario_id"] == "promoted-aaa"
    assert by_idx[3]["user_scenario_id"] == "promoted-bbb"


def test_each_kind_of_scenario_carries_only_its_own_identity():
    """Originals must not carry a promoted id, and vice versa — otherwise a
    verdict could join to both."""
    facade, captured = _facade_with_captured_insert()

    facade.save_forecast_scenario_verdicts("assess-1", [
        _verdict_row(0, scenario_key="k-one"),
        _verdict_row(1, user_scenario_id="promoted-aaa"),
    ])

    original, promoted = captured["payload"]
    assert original["user_scenario_id"] is None
    assert promoted["scenario_key"] is None


def test_two_promoted_scenarios_keep_distinct_ids():
    """The failure this replaces: two addendums resolving to the same or
    swapped identities because the pairing was positional."""
    facade, captured = _facade_with_captured_insert()

    facade.save_forecast_scenario_verdicts("assess-1", [
        _verdict_row(0, user_scenario_id="promoted-aaa"),
        _verdict_row(1, user_scenario_id="promoted-bbb"),
    ])

    ids = [p["user_scenario_id"] for p in captured["payload"]]
    assert ids == ["promoted-aaa", "promoted-bbb"]
    assert len(set(ids)) == 2


# ── Status write contract ───────────────────────────────────────────────


def test_status_write_rejects_mixing_promoted_and_original_identity():
    from app.database_query_facade import DatabaseQueryFacade

    facade = DatabaseQueryFacade.__new__(DatabaseQueryFacade)
    facade.logger = Mock()

    with pytest.raises(ValueError):
        facade.save_forecast_scenario_status(
            RUN, user_scenario_id="u1", scenario_key="k1", status="done")


def test_status_write_requires_some_identity():
    from app.database_query_facade import DatabaseQueryFacade

    facade = DatabaseQueryFacade.__new__(DatabaseQueryFacade)
    facade.logger = Mock()

    with pytest.raises(ValueError):
        facade.save_forecast_scenario_status(RUN, status="done")


# ── Schema contract ─────────────────────────────────────────────────────


def test_scenario_status_has_constraints_that_can_actually_fire():
    """The old UNIQUE(run_id, scenario_idx, user_scenario_id) never fired: one
    of those columns is always NULL and Postgres treats NULLs as distinct."""
    from app.database_models import t_forecast_scenario_status

    constraint_names = {c.name for c in t_forecast_scenario_status.constraints}
    assert "uq_scenario_status_run_keys" not in constraint_names, (
        "the inert three-column unique constraint is still defined"
    )

    index_names = {i.name for i in t_forecast_scenario_status.indexes}
    assert {"uq_scenario_status_key", "uq_scenario_status_addendum",
            "uq_scenario_status_legacy_idx"} <= index_names

    for name in ("uq_scenario_status_key", "uq_scenario_status_addendum",
                 "uq_scenario_status_legacy_idx"):
        idx = next(i for i in t_forecast_scenario_status.indexes if i.name == name)
        assert idx.unique, f"{name} must be unique to prevent duplicate status rows"
        assert idx.dialect_options["postgresql"]["where"] is not None, (
            f"{name} must be partial, or it would forbid legitimate NULL-keyed rows"
        )


def test_scenario_status_requires_one_identity():
    from app.database_models import t_forecast_scenario_status

    checks = {
        c.name for c in t_forecast_scenario_status.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_scenario_status_one_identity" in checks


def test_identity_columns_are_exposed_to_the_api():
    """The API hydrates verdicts with select(table), so the columns being
    present is what puts the identities into the response the UI joins on."""
    from app.database_models import (
        t_forecast_scenario_status, t_forecast_scenario_verdicts,
    )

    assert "user_scenario_id" in t_forecast_scenario_verdicts.c
    assert "scenario_key" in t_forecast_scenario_verdicts.c
    assert "scenario_key" in t_forecast_scenario_status.c
    assert {i.name for i in t_forecast_scenario_verdicts.indexes} >= {
        "ix_scenario_verdicts_user_scenario", "ix_scenario_verdicts_scenario_key",
    }


# ── Deck vs raw granularity ─────────────────────────────────────────────


def _overlay_for(titles, key="deck_key_one"):
    return {
        "topic": "T",
        "deck_scenarios": {key: {"deck_scenario_name": "Collapsed deck scenario",
                                 "horizon": "h1"}},
        "scenario_title_to_deck_key": {t: key for t in titles},
    }


def test_key_derivation_uses_the_list_the_assessment_actually_scores():
    """A run has two scenario lists: the raw one the forecast stored, and the
    deck one that collapses overlapping raw scenarios into the named scenarios
    the customer's deck shows. Whenever the topic has an overlay the deck list
    is what gets assessed, and its titles, order and length all differ from the
    raw list.

    patch_scenario_status derived keys from the RAW list while assess_run
    stamped them from the DECK list. The two key sets had zero entries in
    common, so marking a scenario done returned 409 for every topic with an
    overlay. Both sides now go through build_original_scenarios.
    """
    from app.services.forecast_assessment_service import build_original_scenarios

    raw = [
        {"title": "Raw one", "type": "h1"},
        {"title": "Raw two", "type": "h1"},
        {"title": "Raw three", "type": "h2"},
    ]
    overlay = _overlay_for(["Raw one", "Raw two", "Raw three"])

    deck_list, level = build_original_scenarios("run-1", raw, overlay, topic="T")
    assert level == "deck", "the overlay should have collapsed the raw scenarios"
    assert len(deck_list) < len(raw), "deck granularity should collapse"

    deck_keys = {s["scenario_key"] for s in deck_list}
    raw_keys, raw_level = build_original_scenarios("run-1", raw, None, topic="T")
    assert raw_level == "db"
    assert deck_keys.isdisjoint({s["scenario_key"] for s in raw_keys}), (
        "this is the trap: the two lists genuinely produce different keys"
    )

    # ...so the only safe thing is that every caller builds the list the same
    # way. A second call with the same inputs must reproduce the same keys.
    again, _ = build_original_scenarios("run-1", raw, overlay, topic="T")
    assert {s["scenario_key"] for s in again} == deck_keys


def test_a_stale_overlay_falls_back_to_raw_consistently():
    """When an overlay matches none of the run's titles the assessment falls
    back to raw scenarios. The status route must fall back identically."""
    from app.services.forecast_assessment_service import build_original_scenarios

    raw = [{"title": "Raw one", "type": "h1"}]
    stale = _overlay_for(["Some title from a different run"])

    scenarios, level = build_original_scenarios("run-1", raw, stale, topic="T")

    assert level == "db"
    assert [s["title"] for s in scenarios] == ["Raw one"]
