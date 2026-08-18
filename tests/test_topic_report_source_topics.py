"""A Topic Report rerun must look for articles under the topic's source topics.

The Add-Topic wizard decouples a tracked topic's deck name from the article
``topic`` tag: an analyst can name the topic "Quantum Advantage" while the seed
articles stay tagged "Quantum Computing". ``forecast_topic_metadata.source_topics``
records that mapping, and the forecast assessment path already honours it.

``_rerun_future_horizons_for_topic`` did not. It queried ``WHERE topic = :topic``
with the deck name, got zero rows for any decoupled topic, and raised
"No on-topic articles ... can't run Three Horizons" — so those topics could not
be rerun from Topic Reports at all.

These tests capture the SQL and parameters the rerun issues rather than running
it: the real function calls an LLM and writes to the database. See
tests/conftest.py for why tests here must not touch live state.
"""

import asyncio
from unittest.mock import Mock

import pytest

TRACKED = "Quantum Advantage"
SOURCE = "Quantum Computing"


def _run_and_capture(monkeypatch, source_topics):
    """Record the article query the rerun issues.

    The query returns nothing, so the rerun stops at its own empty-corpus check
    before reaching the model call — which is exactly the failure a decoupled
    topic used to hit, and it leaves the SQL and parameters to assert on.
    """
    import app.database as appdb
    import app.services.topic_report_service as svc

    captured = {}

    def _capture_exec(sql, params=None):
        captured["sql"] = str(sql)
        captured["params"] = params or {}
        return Mock(fetchall=lambda: [])

    facade = Mock()
    facade.get_forecast_topic_metadata.return_value = {"source_topics": source_topics}
    facade._execute_with_rollback = _capture_exec
    db = Mock()
    db.facade = facade
    monkeypatch.setattr(appdb, "get_database_instance", lambda: db)
    monkeypatch.setattr(
        svc, "filter_report_corpus", lambda rows, topic=None: rows, raising=False,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(svc._rerun_future_horizons_for_topic(TRACKED, "gpt-5.4"))

    return captured


def test_rerun_queries_the_source_topics_not_the_deck_name(monkeypatch):
    """The whole failure: a decoupled topic found nothing under its own name."""
    captured = _run_and_capture(monkeypatch, [SOURCE])

    assert "topic = ANY(:topics)" in captured["sql"], (
        "the query must match any of the source topics, not one exact topic"
    )
    assert captured["params"]["topics"] == [SOURCE]
    assert TRACKED not in captured["params"]["topics"]


def test_rerun_falls_back_to_the_tracked_topic_when_no_sources(monkeypatch):
    """Topics whose name already matches the article tag keep working."""
    captured = _run_and_capture(monkeypatch, None)

    assert captured["params"]["topics"] == [TRACKED]


def test_blank_source_topics_are_ignored(monkeypatch):
    """An empty or whitespace-only list must not produce a query for ''."""
    captured = _run_and_capture(monkeypatch, ["", "   "])

    assert captured["params"]["topics"] == [TRACKED]


def test_multiple_source_topics_are_all_searched(monkeypatch):
    captured = _run_and_capture(monkeypatch, [SOURCE, "Photonics"])

    assert captured["params"]["topics"] == [SOURCE, "Photonics"]


def test_ordering_is_fully_deterministic(monkeypatch):
    """Articles from different source topics interleave, so without a final
    tie-break the numbered citations could differ between two runs over
    identical data."""
    captured = _run_and_capture(monkeypatch, [SOURCE, "Photonics"])

    order_by = captured["sql"].split("ORDER BY")[1]
    assert "uri ASC" in order_by, "a unique tie-break key is required"


def test_error_message_names_the_topics_that_were_searched(monkeypatch):
    """Do not silently report 'no articles' without saying where we looked."""
    import app.database as appdb
    import app.services.topic_report_service as svc

    facade = Mock()
    facade.get_forecast_topic_metadata.return_value = {"source_topics": [SOURCE]}
    facade._execute_with_rollback = lambda sql, params=None: Mock(fetchall=lambda: [])
    db = Mock()
    db.facade = facade
    monkeypatch.setattr(appdb, "get_database_instance", lambda: db)
    monkeypatch.setattr(
        svc, "filter_report_corpus", lambda rows, topic=None: rows, raising=False,
    )

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(svc._rerun_future_horizons_for_topic(TRACKED, "gpt-5.4"))

    assert SOURCE in str(exc.value)
