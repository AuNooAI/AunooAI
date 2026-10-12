"""Press events are dated by when the development happened, not when it was
reported (Cisco closed its Astrix purchase on 29 June 2026; an 8 October
article recalling it led October's market moves)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services import market_post_review as mpr
from app.services.entity_event_extractors import coverage

PUBLISHED = datetime(2026, 10, 8, tzinfo=timezone.utc)


def test_a_stated_day_is_kept():
    assert mpr.happened_reading("2026-06-29", PUBLISHED) == ("2026-06-29", "day")


def test_a_stated_month_is_kept_as_a_month():
    assert mpr.happened_reading("2026-06", PUBLISHED) == ("2026-06-01", "month")


def test_the_publication_month_alone_is_not_a_date():
    assert mpr.happened_reading("2026-10", PUBLISHED) == (None, None)


def test_a_date_after_publication_is_dropped():
    assert mpr.happened_reading("2026-11-02", PUBLISHED) == (None, None)


def test_a_founding_year_is_not_the_event():
    assert mpr.happened_reading("2015-03-01", PUBLISHED) == (None, None)


def test_null_and_junk_mean_use_the_publication_date():
    for value in (None, "", "null", "June 29", "2026-13-01"):
        assert mpr.happened_reading(value, PUBLISHED) == (None, None)


def test_the_extractor_reads_the_stored_date():
    day, precision = coverage._happened(
        {"happened": {"date": "2026-06-29", "precision": "day"}})
    assert day == datetime(2026, 6, 29, tzinfo=timezone.utc)
    assert precision == "day"


def test_no_reading_leaves_the_publication_date():
    assert coverage._happened(None) == (None, None)
    assert coverage._happened({"happened": {"date": None}}) == (None, None)
    assert coverage._happened({"press": {}}) == (None, None)
