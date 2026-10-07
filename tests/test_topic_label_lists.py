"""Topic saves refuse an empty label list unless analysis is switched off on purpose."""
from app.services.topic_label_lists import empty_label_lists, label_list_error

FULL = {"name": "T", "categories": ["A"], "future_signals": ["S"], "sentiment": ["Neutral"],
        "time_to_impact": ["Short"], "driver_types": ["Tech"]}


def test_full_topic_passes():
    assert empty_label_lists(FULL) == []
    assert label_list_error(FULL) == ""


def test_each_of_the_five_lists_is_checked():
    for key in ("categories", "future_signals", "sentiment", "time_to_impact", "driver_types"):
        for bad in ([], [""], ["  "], None, "A"):
            topic = {**FULL, key: bad}
            assert empty_label_lists(topic) == [key]
            assert key in label_list_error(topic)
        missing = {k: v for k, v in FULL.items() if k != key}
        assert empty_label_lists(missing) == [key]


def test_explicit_opt_out_is_allowed():
    assert label_list_error({**FULL, "categories": [], "enrichment_disabled": True}) == ""


def test_values_are_not_changed():
    topic = {**FULL, "sentiment": [" Neutral "]}
    label_list_error(topic)
    assert topic["sentiment"] == [" Neutral "]
