"""One definition of what a notification filter means.

The v2 pipeline writes exactly two detection types: ``llm_proposed`` for a newly
proposed theme and ``ongoing_topic`` for one that already had coverage before
the analysis window. ``accelerating`` is a *velocity* state, not a detection
type — comparing it against ``detection_type`` never matched anything, so the
shipped default settings (``["accelerating", "new_cluster"]``) selected no v2
topic at all and the alerts went quiet.

The migration defaults, the monitor, the API validator, and the UI all read
their vocabulary from here.
"""

from typing import Any, Dict, Iterable, List, Optional

# Detection types the v2 pipeline actually writes.
DETECTION_TYPES = ("llm_proposed", "ongoing_topic")

# Velocity states that may be used as a notification condition.
VELOCITY_STATES = ("accelerating",)

# Everything a stored setting may contain.
ALLOWED_FILTERS = DETECTION_TYPES + VELOCITY_STATES

# What a fresh install should notify on: any newly proposed theme, plus
# anything that is picking up speed.
DEFAULT_FILTERS: List[str] = ["llm_proposed", "accelerating"]

# Values written by v1 and by the pre-fix defaults, and what they mean now.
LEGACY_FILTER_MAP: Dict[str, Optional[str]] = {
    "new_cluster": "llm_proposed",
    "proto_cluster": "llm_proposed",
    "splitting": None,      # v1 concept with no v2 equivalent; dropped
    "accelerating": "accelerating",
}


def normalize_filters(filters: Optional[Iterable[str]]) -> List[str]:
    """Map stored values onto the v2 vocabulary, in order, without duplicates.

    Unknown values are dropped rather than kept, so a stale setting cannot
    silently match nothing. An input that normalizes to nothing at all falls
    back to the defaults.
    """
    if not filters:
        return list(DEFAULT_FILTERS)

    out: List[str] = []
    for raw in filters:
        if raw is None:
            continue
        value = str(raw).strip().lower()
        if value in ALLOWED_FILTERS:
            mapped = value
        elif value in LEGACY_FILTER_MAP:
            mapped = LEGACY_FILTER_MAP[value]
        else:
            mapped = None
        if mapped and mapped not in out:
            out.append(mapped)

    return out or list(DEFAULT_FILTERS)


def validate_filters(filters: Iterable[str]) -> List[str]:
    """Validate submitted filter values, raising on anything unrecognised."""
    unknown = [
        str(f) for f in filters
        if str(f).strip().lower() not in ALLOWED_FILTERS
        and str(f).strip().lower() not in LEGACY_FILTER_MAP
    ]
    if unknown:
        raise ValueError(
            "Unknown notification filter(s): "
            f"{', '.join(sorted(unknown))}. Allowed values: "
            f"{', '.join(ALLOWED_FILTERS)}."
        )
    return normalize_filters(filters)


def topic_matches_filters(topic: Dict[str, Any], filters: Optional[Iterable[str]]) -> bool:
    """True when a detected topic satisfies at least one notification filter.

    Detection-type filters are compared against ``detection_type``; velocity
    filters against ``velocity``. That distinction is the whole point of this
    module.
    """
    normalized = normalize_filters(filters)
    detection_type = str(topic.get("detection_type") or "").strip().lower()
    velocity = str(topic.get("velocity") or "").strip().lower()

    for wanted in normalized:
        if wanted in VELOCITY_STATES:
            if velocity == wanted:
                return True
        elif detection_type == wanted:
            return True
    return False


def select_topics_for_notification(
    topics: Iterable[Dict[str, Any]],
    filters: Optional[Iterable[str]],
    min_confidence: float,
) -> List[Dict[str, Any]]:
    """Topics that pass both the filter set and the confidence floor."""
    return [
        t for t in topics
        if topic_matches_filters(t, filters)
        and float(t.get("confidence_score") or 0) >= min_confidence
    ]
