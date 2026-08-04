"""
Tests for topic-name normalization in Research.

Regression cover for a bug that ran in production for months: config.json held a
topic named "Brand Monitoring Springer " with a trailing space. set_topic()
stripped the name it was asked for, but load_config() built its lookup keys
straight from the file, so the two never matched. On a miss set_topic() returns
early and keeps whatever topic was already selected, so Springer's articles were
analysed under Wiley's and AI/ML's configuration around 3,000 times a day, with
nothing but a log line to show for it.

The fix is that both sides go through normalize_topic_name(). These tests pin
that down from both directions: names are reachable however they are spelled, and
an unknown topic is still rejected.
"""

import types

import pytest

from app.research import Research, normalize_topic_name


@pytest.fixture
def research(monkeypatch):
    """A Research stub wired to a config we control.

    Research.__init__ pulls in the analyzer, the database facade and the
    collectors, none of which this behaviour depends on, so the methods are
    called against a namespace carrying just the attributes they touch.
    """
    def _build(topics):
        import app.config.config as cfgmod
        monkeypatch.setattr(cfgmod, "load_config", lambda: {"topics": topics})
        stub = types.SimpleNamespace(
            topic_configs={},
            current_topic=Research.DEFAULT_TOPIC,
            DEFAULT_TOPIC=Research.DEFAULT_TOPIC,
        )
        Research.load_config(stub)
        return stub
    return _build


DEFAULT = {"name": Research.DEFAULT_TOPIC, "categories": []}


class TestNormalizeTopicName:
    @pytest.mark.parametrize("raw,expected", [
        ("Brand Monitoring Springer ", "Brand Monitoring Springer"),
        (" Brand Monitoring Springer", "Brand Monitoring Springer"),
        ("Brand  Monitoring   Springer", "Brand Monitoring Springer"),
        ("Brand\nMonitoring Springer", "Brand Monitoring Springer"),
        ("Brand\tMonitoring Springer", "Brand Monitoring Springer"),
        ("Brand Monitoring Springer", "Brand Monitoring Springer"),
    ])
    def test_collapses_whitespace(self, raw, expected):
        assert normalize_topic_name(raw) == expected

    @pytest.mark.parametrize("falsy", ["", None])
    def test_passes_through_empty(self, falsy):
        assert normalize_topic_name(falsy) == falsy


class TestLoadConfigKeys:
    def test_key_is_normalized(self, research):
        r = research([DEFAULT, {"name": "Brand Monitoring Springer ", "categories": ["a"]}])
        assert "Brand Monitoring Springer" in r.topic_configs
        assert "Brand Monitoring Springer " not in r.topic_configs

    def test_entry_name_is_normalized_too(self, research):
        """The entry's own name is written onto the rows this topic produces, so
        leaving it unclean would put the bad value straight back in the database."""
        r = research([DEFAULT, {"name": "Brand Monitoring Springer ", "categories": ["a"]}])
        assert r.topic_configs["Brand Monitoring Springer"]["name"] == "Brand Monitoring Springer"

    def test_names_that_normalize_alike_do_not_silently_overwrite(self, research):
        r = research([DEFAULT,
                      {"name": "Dup Topic ", "categories": ["first"]},
                      {"name": " Dup  Topic", "categories": ["second"]}])
        assert list(r.topic_configs).count("Dup Topic") == 1
        assert r.topic_configs["Dup Topic"]["categories"] == ["first"]

    def test_nameless_topic_is_skipped_not_fatal(self, research):
        """A whitespace-only name used to raise inside load_config, and the caller
        catches that by falling back to a single default topic — losing all of them."""
        r = research([DEFAULT, {"name": "   ", "categories": []}, {"categories": []}])
        assert list(r.topic_configs) == [Research.DEFAULT_TOPIC]


class TestSetTopic:
    @pytest.mark.parametrize("asked", [
        "Brand Monitoring Springer",
        "Brand Monitoring Springer ",
        "  Brand Monitoring   Springer  ",
        "Brand\nMonitoring Springer",
    ])
    def test_resolves_however_it_is_spelled(self, research, asked):
        r = research([DEFAULT, {"name": "Brand Monitoring Springer ", "categories": ["a"]}])
        Research.set_topic(r, asked)
        assert r.current_topic == "Brand Monitoring Springer"

    def test_config_stored_clean_still_matches_a_legacy_spaced_caller(self, research):
        """Anything holding the old spaced name keeps working after the rename."""
        r = research([DEFAULT, {"name": "Brand Monitoring Springer", "categories": ["a"]}])
        Research.set_topic(r, "Brand Monitoring Springer ")
        assert r.current_topic == "Brand Monitoring Springer"

    def test_unknown_topic_is_still_rejected(self, research):
        r = research([DEFAULT, {"name": "Brand Monitoring Springer", "categories": ["a"]}])
        Research.set_topic(r, "No Such Topic")
        assert r.current_topic == Research.DEFAULT_TOPIC

    def test_empty_topic_is_ignored(self, research):
        r = research([DEFAULT, {"name": "Brand Monitoring Springer", "categories": ["a"]}])
        Research.set_topic(r, "")
        assert r.current_topic == Research.DEFAULT_TOPIC
