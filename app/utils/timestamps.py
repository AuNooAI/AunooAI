"""One shape for ``articles.submission_date``.

The column is text. PostgreSQL fills it with ``CURRENT_TIMESTAMP`` when a
writer leaves it out, which prints as ``2026-08-28 13:00:24.580955+02``:
local time (the database runs on Europe/Berlin) with the UTC offset. Most
rows have that shape. A few writers used to stamp ISO ``T...Z`` UTC, a
naive ``T`` time, or a bare date, and because ``T`` sorts after a space,
text comparisons such as ``max()`` or ``>= '2026-08-28 12:00'`` silently
dropped rows from the same day. Every writer now goes through
``submission_stamp`` so every row has the database's own shape.
"""
from __future__ import annotations

import logging
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
