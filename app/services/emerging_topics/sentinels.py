"""Normalize the "no value" strings LLMs return.

The deep-analysis prompt tells the model to write "Not mentioned" when the
articles do not support a field. Those strings are truthy, so a topic with no
identified actors and no trigger event scored the same confidence as one with
both. Everything here turns such a placeholder into an actually empty value
before it reaches scoring or the database.
"""

from typing import Any, Dict, List, Optional

# Compared case-insensitively after stripping whitespace and trailing periods.
SENTINEL_VALUES = frozenset({
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "none mentioned",
    "none identified",
    "none specified",
    "not applicable",
    "not available",
    "not identified",
    "not mentioned",
    "not mentioned in articles",
    "not specified",
    "not stated",
    "null",
    "unknown",
    "unspecified",
})


def is_sentinel(value: Any) -> bool:
    """True when a value carries no information."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().strip(".").strip().lower() in SENTINEL_VALUES
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def clean_text(value: Any) -> str:
    """Return the text, or "" when it is a placeholder."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return "" if is_sentinel(value) else value.strip()


def clean_list(value: Any) -> List[str]:
    """Return a list of substantive strings, dropping placeholders.

    Non-list input becomes a single-item list (or an empty one). Dict items are
    flattened to their values, which is how some models answer a "list of
    names" instruction.
    """
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = clean_text(value)
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, (list, tuple, set)):
        cleaned = clean_text(value)
        return [cleaned] if cleaned else []

    out = []
    for item in value:
        if isinstance(item, dict):
            item = " - ".join(str(v) for v in item.values() if v)
        cleaned = clean_text(item)
        if cleaned:
            out.append(cleaned)
    return out


def clean_str_dict(value: Any) -> Dict[str, str]:
    """Clean a flat {field: text} mapping, dropping empty fields."""
    if not isinstance(value, dict):
        return {}
    return {k: clean_text(v) for k, v in value.items()}


def clean_list_dict(value: Any) -> Dict[str, List[str]]:
    """Clean a {field: [items]} mapping."""
    if not isinstance(value, dict):
        return {}
    return {k: clean_list(v) for k, v in value.items()}


def has_substance(value: Any) -> bool:
    """True when a value survives cleaning with something in it."""
    if isinstance(value, dict):
        return any(has_substance(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return bool(clean_list(value))
    return bool(clean_text(value))


def clean_events(events: Any) -> Dict[str, Any]:
    """Clean the deep-analysis events block, keeping its shape."""
    if not isinstance(events, dict):
        return {}
    return {
        "trigger_event": clean_text(events.get("trigger_event")),
        "timeline": clean_list(events.get("timeline")),
        "current_status": clean_text(events.get("current_status")),
    }


def clean_synthesis(synthesis: Any) -> Dict[str, Any]:
    """Clean the synthesis block, keeping urgency inside its allowed values."""
    if not isinstance(synthesis, dict):
        return {}
    urgency = clean_text(synthesis.get("urgency")).lower()
    if urgency not in {"low", "medium", "high"}:
        urgency = "medium"
    cleaned = {
        "key_takeaway": clean_text(synthesis.get("key_takeaway")),
        "stakeholders_affected": clean_list(synthesis.get("stakeholders_affected")),
        "urgency": urgency,
    }
    # Preserve any extra keys the caller attached (for example model_used).
    for key, value in synthesis.items():
        if key not in cleaned:
            cleaned[key] = value
    return cleaned
