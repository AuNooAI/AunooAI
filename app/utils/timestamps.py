"""One shape for ``articles.submission_date``.

The column is text. PostgreSQL fills it with ``CURRENT_TIMESTAMP`` when a
writer leaves it out, which prints as ``2026-08-28 13:00:24.580955+02``:
local time (the database runs on Europe/Berlin) with the UTC offset. Most
rows have that shape. A few writers used to stamp ISO ``T...Z`` UTC, a
naive ``T`` time, or a bare date, and because ``T`` sorts after a space,
text comparisons such as ``max()`` or ``>= '2026-08-28 12:00'`` silently
dropped rows from the same day. Every writer now goes through
``submission_stamp`` so every row has the database's own shape.

``articles.publication_date`` is text too, and the article's own date. Its
stored shape is ISO 8601 in UTC with an explicit ``+00:00`` offset
(``2026-10-15T14:06:26+00:00``). Collectors hand us other shapes: TheNewsAPI
sends ``2026-10-15T16:32:02.000000Z``, NewsFirehose and NewsData send
``2026-10-15T14:06:26`` with the zone dropped (the time is UTC; Fortune's own
page metadata for one such article reads ``14:06:26-00:00``). A browser reads
a zone-less stamp as local time, so the feed showed those articles one or two
hours early and sorted them out of order. ``publication_stamp`` rewrites every
parseable stamp into the stored shape before insert.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Optional, Union

log = logging.getLogger(__name__)

Stampable = Union[None, str, datetime, date]


def submission_stamp(value: Stampable = None) -> str:
    """The text to store in ``submission_date``.

    ``None`` or an empty string means now. A ``datetime`` is converted to
    local time (a naive one is taken as local already). A string is parsed
    as ISO 8601 (``Z``, an offset, naive, or a bare date, which becomes
    local midnight) and rewritten. A string that does not parse is returned
    as it came, with a warning, so no row is destroyed by this helper.
    """
    if value is None or value == "":
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00") if text.endswith("Z") else text)
        except ValueError:
            log.warning("submission_stamp: cannot parse %r; stored as is", value)
            return text
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive = local wall time
    else:
        dt = dt.astimezone()  # to local
    off = dt.strftime("%z")  # +0200
    offset = off[:3] if off[3:] == "00" else f"{off[:3]}:{off[3:]}"
    return f"{dt:%Y-%m-%d %H:%M:%S.%f}{offset}"


def is_submission_stamp(text: Optional[str]) -> bool:
    """True when ``text`` already has the stored shape."""
    import re
    return bool(text) and re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}(:\d{2})?", text) is not None


_DAY_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")


def publication_stamp(value: Stampable) -> Optional[str]:
    """The text to store in ``articles.publication_date``.

    ``None`` or an empty string stays ``None``: an unknown date is never
    replaced with now. A bare date (``2026-10-08``) is returned as it came,
    because it means a day, not an instant. A ``datetime`` or any ISO 8601
    string (``Z``, an offset, fractional seconds, a space or ``T`` separator)
    becomes ``YYYY-MM-DDTHH:MM:SS+00:00`` in UTC. A string without a zone is
    taken as UTC, which is what every collector that drops the zone sends. A
    string that does not parse is returned as it came, with a warning, so no
    row is destroyed by this helper.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        return value.isoformat()
    else:
        text = str(value).strip()
        if not text:
            return None
        if _DAY_ONLY.fullmatch(text):
            return text
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00") if text.endswith("Z") else text)
        except ValueError:
            log.warning("publication_stamp: cannot parse %r; stored as is", value)
            return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def is_publication_stamp(text: Optional[str]) -> bool:
    """True when ``text`` already has the stored shape."""
    return bool(text) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", text) is not None
