"""Publication-timestamp handling for the emerging-topics pipeline.

``articles.publication_date`` is a TEXT column. It holds a mix of ISO-8601
timestamps (with and without a trailing ``Z`` or an offset), plain
``YYYY-MM-DD`` dates, and the occasional unparseable value. Casting the whole
column with ``::timestamp`` aborts the entire query on the first malformed row,
so both the SQL and the Python side go through the helpers here.

Two entry points:

* :func:`publication_ts_sql` builds a guarded SQL expression that yields a
  timestamp for rows that look like a date and NULL for everything else. It
  never raises, so one bad row cannot take a query down.
* :func:`parse_publication_timestamp` is the Python equivalent. It always
  returns a timezone-aware UTC datetime, so callers can compare values without
  the naive/aware mismatch that used to silently drop articles.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

# A date prefix we are willing to hand to to_timestamp. Month and day ranges are
# checked in the pattern itself so the cast cannot fail on "2026-13-45".
_DATE_PREFIX = r'^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])'
# ... optionally followed by a full HH:MM:SS time, separated by "T" or a space.
_DATETIME_PREFIX = _DATE_PREFIX + r'[T ][0-2][0-9]:[0-5][0-9]:[0-5][0-9]'

_NAIVE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
)


def publication_ts_sql(column: str = "publication_date") -> str:
    """Return a SQL expression converting a text date column to a timestamp.

    Rows whose text does not start with a plausible ``YYYY-MM-DD`` prefix come
    back as NULL rather than aborting the statement. The time of day is kept
    when the value carries one.

    ``column`` is an identifier chosen by this module's callers (for example
    ``"a.publication_date"``), never user input.
    """
    return (
        "CASE "
        f"WHEN {column} ~ '{_DATETIME_PREFIX}' "
        f"THEN to_timestamp(replace(substring({column} from 1 for 19), 'T', ' '), "
        "'YYYY-MM-DD HH24:MI:SS') "
        f"WHEN {column} ~ '{_DATE_PREFIX}' "
        f"THEN to_timestamp(substring({column} from 1 for 10), 'YYYY-MM-DD') "
        "END"
    )


def parse_publication_timestamp(value: Any) -> Optional[datetime]:
    """Parse an article publication date into a timezone-aware UTC datetime.

    Accepts datetimes, dates, ISO-8601 strings with ``Z`` or a numeric offset,
    plain dates, and a few legacy formats. Returns ``None`` for anything it
    cannot read, including ``None`` and empty strings. Naive values are read as
    UTC, which is how the collectors write them.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

    text_value = str(value).strip()
    if not text_value:
        return None

    iso_candidate = text_value
    if iso_candidate.endswith(("Z", "z")):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt in _NAIVE_FORMATS:
        try:
            return datetime.strptime(text_value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Last resort: an ISO date prefix on an otherwise unreadable string.
    try:
        return datetime.strptime(text_value[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)
