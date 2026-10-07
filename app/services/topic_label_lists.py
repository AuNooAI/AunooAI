"""The five label lists every analysed topic needs.

The AI analysis step picks each article's labels from these lists. A topic
saved with one of them empty or missing gets its articles stored but never
analysed, so the save paths refuse it unless the caller sets
``enrichment_disabled`` on purpose. This checks the lists; it never changes
their values.
"""
from typing import Dict, List

LABEL_LISTS = ("categories", "future_signals", "sentiment", "time_to_impact", "driver_types")


def empty_label_lists(topic: Dict) -> List[str]:
    """Names of the label lists that are missing, empty, or hold only blanks."""
    empty = []
    for key in LABEL_LISTS:
        values = topic.get(key)
        if not isinstance(values, list) or not any(str(v).strip() for v in values):
            empty.append(key)
    return empty


def label_list_error(topic: Dict) -> str:
    """The refusal message for a topic with empty lists, or "" when it is fine."""
    if topic.get("enrichment_disabled"):
        return ""
    empty = empty_label_lists(topic)
    if not empty:
        return ""
    return (
        f"Topic '{topic.get('name', '')}' has an empty {', '.join(empty)} list. "
        "Articles for a topic without these lists are stored but never analysed. "
        "Fill the list, or send enrichment_disabled: true to save it that way on purpose."
    )
