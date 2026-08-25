"""Stable identity for forecast scenarios.

A scenario's ``scenario_idx`` is only its position in the list ``assess_run``
builds — the run's original scenarios followed by any promoted ones. That
position moves when a promoted scenario is added or skipped, and it means
different things in different runs, so it cannot be the key that status and
verdicts hang off.

Two kinds of scenario, two kinds of identity:

* **Promoted** scenarios already have a row of their own in
  ``forecast_user_scenarios``, so their UUID is the key.
* **Original** scenarios live inside ``future_horizons_runs.raw_output``, which
  is immutable history. Newly persisted runs get a ``scenario_key`` stamped in
  (see :func:`ensure_scenario_keys`); runs stored before that get the same key
  *derived* on every read from content that cannot change — the run id, the
  horizon, the normalized title, and the scenario's original position. Derived
  and stamped keys are produced by the same function, so a run keeps one
  identity whether or not it was stamped.

The derivation deliberately includes the index. Titles are not unique within a
run (decks repeat a heading across horizons), and without it two scenarios
could collapse onto one key and share status.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Iterable, Optional

# Version prefix so a future change to the derivation is distinguishable in the
# data rather than silently re-pointing existing rows.
_DERIVED_PREFIX = "d1"


def normalize_title(title: Optional[str]) -> str:
    """Reduce a title to letters and digits only, casefolded.

    Separators are removed rather than collapsed to a space, so "1,000" and
    "1000", and "fault-tolerant" and "fault tolerant", reduce to the same thing.
    Replacing them with a space would keep those apart and change a scenario's
    identity over a thousands separator. The result is only ever hashed, so it
    does not need to stay readable.
    """
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def derive_scenario_key(run_id: str, scenario: dict, index: int) -> str:
    """Deterministic key for an original scenario of a stored run.

    Same inputs always give the same key, so a legacy run's scenarios can be
    identified without rewriting the run.
    """
    horizon = str(scenario.get("type") or scenario.get("horizon_type") or "").lower()
    basis = "|".join([
        str(run_id or ""),
        horizon,
        normalize_title(scenario.get("title")),
        str(index),
    ])
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]
    return f"{_DERIVED_PREFIX}:{digest}"


def scenario_key_for(run_id: str, scenario: dict, index: int) -> str:
    """The scenario's key: the stamped one if present, otherwise derived."""
    existing = scenario.get("scenario_key")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    return derive_scenario_key(run_id, scenario, index)


def ensure_scenario_keys(run_id: str, scenarios: Iterable[Any]) -> list:
    """Stamp a ``scenario_key`` onto each scenario of a run being persisted.

    Called on the write path for new runs so their keys are explicit in
    ``raw_output`` rather than derived. Existing keys are left alone, so calling
    this twice is safe. Returns the same list of dicts, mutated in place;
    non-dict entries are passed through untouched rather than raising, because
    ``raw_output`` shapes vary across model versions.
    """
    out = []
    for i, scenario in enumerate(scenarios or []):
        if isinstance(scenario, dict) and not scenario.get("scenario_key"):
            # New runs get a plain UUID: nothing to be compatible with yet, and
            # it stays stable even if the title is later edited in place.
            scenario["scenario_key"] = uuid.uuid4().hex
        out.append(scenario)
    return out


def index_scenarios_by_key(run_id: str, scenarios: Iterable[Any]) -> dict:
    """Map ``scenario_key -> (index, scenario)`` for a run's original scenarios."""
    out = {}
    for i, scenario in enumerate(scenarios or []):
        if not isinstance(scenario, dict):
            continue
        out[scenario_key_for(run_id, scenario, i)] = (i, scenario)
    return out
