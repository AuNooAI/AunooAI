"""The MBFC lookup reads sources; it never switches a disabled one back on."""
import logging

from app.models.media_bias import MediaBias


class _Facade:
    def __init__(self):
        self.enabled_calls = []

    def enable_media_source(self, source):
        self.enabled_calls.append(source)


class _Db:
    def __init__(self):
        self.facade = _Facade()


def _mb(sources):
    mb = MediaBias.__new__(MediaBias)
    mb.db = _Db()
    mb.logger = logging.getLogger("test.mbfc")
    mb.sources = sources
    return mb


def test_disabled_source_is_skipped_and_left_disabled():
    src = {"source": "example.com", "enabled": 0, "bias": "Left"}
    mb = _mb([src])
    assert mb.get_bias_for_source("https://example.com/story") is None
    assert mb.db.facade.enabled_calls == []
    assert src["enabled"] == 0


def test_enabled_source_is_found():
    mb = _mb([{"source": "example.com", "enabled": 1, "bias": "Left"}])
    assert mb.get_bias_for_source("example.com")["bias"] == "Left"
