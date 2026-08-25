"""Feature flags for the entity-intelligence rollout, read in one place.

Six switches control how much of the new path is live. They are read here and
nowhere else, so that "which flags are on right now" is answerable by calling
one function rather than grepping for ``os.getenv`` across a dozen modules.

The defaults are the safe end of each switch: writes happen, reads do not. A
deployment with no environment changes at all stores observations alongside the
existing behavior and serves the existing behavior, which is what the first
rollout step needs.

Environment is read on each call rather than cached at import. Flipping a flag
should take a restart, not a redeploy, and the cost of a ``getenv`` is nothing
next to the database work it gates.
"""

from __future__ import annotations

import os
from typing import Dict

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# name -> default. Anything not listed here is not a flag, and asking for it
# raises rather than quietly returning False.
_FLAGS: Dict[str, bool] = {
    "ENTITY_INTELLIGENCE_ENABLED": False,
    "ENTITY_INTELLIGENCE_DUAL_WRITE": True,
    "ENTITY_INTELLIGENCE_CANONICAL_READ": False,
    "ENTITY_INTELLIGENCE_MENTION_READ": False,
    "ENTITY_INTELLIGENCE_EVENTS_ENABLED": False,
    "ENTITY_INTELLIGENCE_SOCIAL_ENABLED": False,
}


def _parse(raw: str, default: bool) -> bool:
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def flag(name: str) -> bool:
    """Read one flag. Unknown names raise, so a typo fails loudly."""
    if name not in _FLAGS:
        raise KeyError(f"unknown entity-intelligence flag: {name}")
    raw = os.getenv(name)
    if raw is None:
        return _FLAGS[name]
    return _parse(raw, _FLAGS[name])


def enabled() -> bool:
    """The master switch. Off means no new processing runs at all."""
    return flag("ENTITY_INTELLIGENCE_ENABLED")


def dual_write() -> bool:
    """Keep writing the legacy shapes beside the new ones during rollout."""
    return flag("ENTITY_INTELLIGENCE_DUAL_WRITE")


def canonical_read() -> bool:
    """Serve canonical field values instead of the import baseline."""
    return flag("ENTITY_INTELLIGENCE_CANONICAL_READ")


def mention_read() -> bool:
    """Serve per-entity mention scores instead of article-level columns."""
    return flag("ENTITY_INTELLIGENCE_MENTION_READ")


def events_enabled() -> bool:
    return flag("ENTITY_INTELLIGENCE_EVENTS_ENABLED")


def social_enabled() -> bool:
    return flag("ENTITY_INTELLIGENCE_SOCIAL_ENABLED")


def snapshot() -> Dict[str, bool]:
    """Every flag and its current value, for health endpoints and logs."""
    return {name: flag(name) for name in _FLAGS}
