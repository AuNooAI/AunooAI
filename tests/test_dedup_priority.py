"""Duplicate URLs across providers keep one copy, chosen by a fixed priority."""
from app.tasks.keyword_monitor import KeywordMonitor


def _dedup(rows):
    km = KeywordMonitor.__new__(KeywordMonitor)
    return km._deduplicate_articles(rows)


def _a(src, url="https://x.test/a", **kw):
    return {"url": url, "collector_source": src, **kw}


def test_firehose_copy_wins_whatever_the_order():
    for rows in ([_a("newsapi"), _a("newsfirehose")], [_a("newsfirehose"), _a("newsapi")]):
        out = _dedup(rows)
        assert [r["collector_source"] for r in out] == ["newsfirehose"]


def test_social_sources_have_distinct_priorities():
    out = _dedup([_a("telegram"), _a("xpoz"), _a("reddit")])
    assert [r["collector_source"] for r in out] == ["reddit"]
    out = _dedup([_a("reddit"), _a("bluesky")])
    assert [r["collector_source"] for r in out] == ["bluesky"]


def test_matched_keywords_survive_the_swap():
    out = _dedup([_a("telegram", _matched_keywords=["a"]), _a("newsfirehose", _matched_keywords=["b"])])
    assert out[0]["_matched_keywords"] == ["a", "b"]
