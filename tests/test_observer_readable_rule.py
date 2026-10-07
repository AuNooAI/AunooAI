"""Observer agents read only what readers can see.

The six Observer and signal queries in vector_routes.py used their own
filter (category and sentiment set). It had no relevance floor, no copy
rule and no press-release rule, so on 7 Oct 2026 23% of the 30-day agent pool
on bugfixing (1,485 of 6,343) was rows the readable-articles rule hides. This
guards the queries against losing the shared rule again.
"""
import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "vector_routes.py").read_text()


def test_every_observer_query_applies_the_readable_rule():
    assert SRC.count("readable_sql()") >= 6
    assert "from app.services.article_visibility import agent_evidence_sql, readable_sql" in SRC


def test_no_observer_query_is_category_only():
    """Social posts carry no category; the agents take them through the
    shared clause (relevant, not a false positive). Incident tracking and
    real-time signals were category-only until 7 Oct 2026."""
    assert "AND category IS NOT NULL AND NULLIF(TRIM(sentiment), '') IS NOT NULL" not in SRC
    assert SRC.count("agent_evidence_sql()") >= 2


def test_no_observer_query_accepts_an_empty_sentiment():
    # The old gate was "sentiment IS NOT NULL", which an empty string passes.
    assert SRC.count("NULLIF(TRIM(sentiment), '') IS NOT NULL") >= 6
