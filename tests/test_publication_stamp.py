"""publication_stamp: one shape for articles.publication_date."""
from datetime import date, datetime, timezone, timedelta

from app.utils.timestamps import is_publication_stamp, publication_stamp


def test_thenewsapi_microsecond_z_becomes_offset():
    assert publication_stamp("2026-10-15T16:32:02.000000Z") == "2026-10-15T16:32:02+00:00"


def test_zoneless_stamp_is_utc():
    # Fortune's own metadata for this article reads 2026-10-15T14:06:26-00:00.
    assert publication_stamp("2026-10-15T14:06:26") == "2026-10-15T14:06:26+00:00"


def test_offset_is_converted_to_utc():
    assert publication_stamp("2026-10-15T16:06:26+02:00") == "2026-10-15T14:06:26+00:00"
    assert publication_stamp("2026-10-14T14:08:45.280Z") == "2026-10-14T14:08:45+00:00"


def test_canonical_shape_is_unchanged():
    assert publication_stamp("2026-10-16T06:05:01+00:00") == "2026-10-16T06:05:01+00:00"
    assert is_publication_stamp("2026-10-16T06:05:01+00:00")
    assert not is_publication_stamp("2026-10-16T06:05:01Z")


def test_bare_date_and_date_object_keep_day_precision():
    assert publication_stamp("2026-10-08") == "2026-10-08"
    assert publication_stamp(date(2026, 10, 8)) == "2026-10-08"


def test_datetime_objects():
    aware = datetime(2026, 10, 15, 16, 6, 26, tzinfo=timezone(timedelta(hours=2)))
    assert publication_stamp(aware) == "2026-10-15T14:06:26+00:00"
    assert publication_stamp(datetime(2026, 10, 15, 14, 6, 26)) == "2026-10-15T14:06:26+00:00"


def test_unknown_stays_unknown_and_garbage_passes_through():
    assert publication_stamp(None) is None
    assert publication_stamp("") is None
    assert publication_stamp("   ") is None
    assert publication_stamp("yesterday") == "yesterday"
