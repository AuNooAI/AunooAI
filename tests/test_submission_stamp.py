"""Every article's submission_date has the database's own shape."""
import os
import re
from datetime import datetime, timezone

os.environ.setdefault("TZ", "Europe/Berlin")
import time
time.tzset()

from app.utils.timestamps import is_submission_stamp, submission_stamp

SHAPE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}[+-]\d{2}$")


def test_now_has_the_shape():
    s = submission_stamp()
    assert SHAPE.match(s), s
    assert is_submission_stamp(s)


def test_utc_z_string_converts_to_local():
    assert submission_stamp("2026-08-28T04:25:11.612255Z") == "2026-08-28 06:25:11.612255+02"


def test_utc_datetime_and_offset_string():
    assert submission_stamp(datetime(2026, 1, 7, 11, 25, 15, 505003, tzinfo=timezone.utc)) == "2026-01-07 12:25:15.505003+01"
    assert submission_stamp("2026-08-27T18:55:55+00:00") == "2026-08-27 20:55:55.000000+02"


def test_naive_and_date_only_are_local():
    assert submission_stamp("2026-08-28 13:00:12") == "2026-08-28 13:00:12.000000+02"
    assert submission_stamp("2025-10-15") == "2025-10-15 00:00:00.000000+02"
    assert submission_stamp(datetime(2026, 8, 28, 13, 0, 12)) == "2026-08-28 13:00:12.000000+02"


def test_stored_shape_passes_through_unchanged():
    s = "2026-08-28 13:00:24.580955+02"
    assert submission_stamp(s) == s


def test_garbage_is_left_alone():
    assert submission_stamp("yesterday") == "yesterday"
    assert not is_submission_stamp("yesterday") and not is_submission_stamp("")
