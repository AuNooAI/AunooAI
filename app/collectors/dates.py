"""One date parser for every collector, with precision and provenance.

A missing or unparseable publication date used to become "now". That makes
a 2023 Bluesky post look like today's news, and it makes it impossible to
tell afterwards which dates were real. The rules here:

- Missing or invalid input stays unknown. Nothing substitutes the current
  time; discovery views use ``first_seen_at`` for that.
- Precision is kept. A ``2026-09-30`` is a day, not midnight; a ``2026-09``
  is a month. If storage needs one instant for a coarse date, callers take
  ``representative_instant`` and store the precision beside it.
- A timestamp without a zone is only assumed UTC where the provider's
  documentation says so (``assume_utc=True``), and the result says it was
  assumed.
- Future dates are kept and flagged, never clamped.

Identical in both repositories; import nothing from either application.
"""
from __future__ import annotations

import calendar
import re
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional, Sequence

PREC_SECOND = "second"
PREC_MINUTE = "minute"
PREC_DAY = "day"
PREC_MONTH = "month"
PREC_YEAR = "year"

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_INVALID = "invalid"

#: Provenance labels. Stored next to the date so a reader knows what it is.
PROV_PROVIDER = "provider"          # the provider's own publication field
PROV_FEED = "feed"                  # RSS/Atom published/updated
PROV_INDEXED = "source_indexed"     # when the provider indexed it, not wrote it
PROV_MODEL = "model_extracted"      # a model read it off the page
PROV_WAYBACK = "wayback_first_capture"
PROV_UNKNOWN = "unknown"

_ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_ISO_YEAR = re.compile(r"^(\d{4})$")
_COMPACT_DAY = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


@dataclass
class ParsedDate:
    value: Optional[datetime]           # UTC-aware when known
    raw: Optional[str]
    precision: Optional[str]
    provenance: str
    status: str
    tz_assumed: bool = False

    @property
    def known(self) -> bool:
        return self.value is not None

    @property
    def exact(self) -> bool:
        return self.precision in (PREC_SECOND, PREC_MINUTE)

    def iso(self) -> Optional[str]:
        return self.value.isoformat() if self.value else None

    def is_future(self, now: Optional[datetime] = None, tolerance: timedelta = timedelta(days=1)) -> bool:
        if self.value is None:
            return False
        return self.value > (now or datetime.now(timezone.utc)) + tolerance

    def as_fields(self, prefix: str = "") -> dict:
        """Column values for the proposed schema: published_at,
        published_at_raw, publication_date_precision, date_provenance."""
        return {
            f"{prefix}published_at": self.value,
            f"{prefix}published_at_raw": self.raw,
            f"{prefix}publication_date_precision": self.precision,
            f"{prefix}date_provenance": self.provenance if self.value else PROV_UNKNOWN,
        }


def unknown(raw: Any = None, *, provenance: str = PROV_UNKNOWN, status: str = STATUS_MISSING) -> ParsedDate:
    return ParsedDate(value=None, raw=_raw_text(raw), precision=None, provenance=provenance, status=status)


def _raw_text(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, (datetime, date)):
        return raw.isoformat()
    text = str(raw).strip()
    return text[:200] if text else None


def _aware(dt: datetime, assume_utc: bool) -> "tuple[Optional[datetime], bool]":
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc), False
    if assume_utc:
        return dt.replace(tzinfo=timezone.utc), True
    return None, False


def parse_date(raw: Any, *, provenance: str = PROV_PROVIDER, assume_utc: bool = False,
               formats: Sequence[str] = ()) -> ParsedDate:
    """Parse anything a provider hands us. Never raises, never invents."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return unknown(raw, provenance=provenance, status=STATUS_MISSING)

    # Already a datetime (SDK objects).
    if isinstance(raw, datetime):
        value, assumed = _aware(raw, assume_utc)
        if value is None:
            return ParsedDate(None, _raw_text(raw), None, provenance, STATUS_INVALID)
        prec = PREC_SECOND if (raw.second or raw.microsecond) else PREC_MINUTE if (raw.hour or raw.minute) else PREC_SECOND
        return ParsedDate(value, _raw_text(raw), prec, provenance, STATUS_OK, assumed)
    if isinstance(raw, date):
        value = datetime(raw.year, raw.month, raw.day, tzinfo=timezone.utc)
        return ParsedDate(value, _raw_text(raw), PREC_DAY, provenance, STATUS_OK)

    # feedparser's struct_time is already UTC.
    if isinstance(raw, _time.struct_time):
        try:
            value = datetime.fromtimestamp(calendar.timegm(raw), tz=timezone.utc)
        except (OverflowError, ValueError):
            return ParsedDate(None, _raw_text(raw), None, provenance, STATUS_INVALID)
        return ParsedDate(value, value.isoformat(), PREC_SECOND, provenance, STATUS_OK)

    # Crossref-style date parts: [[2026, 9, 30]] or [2026, 9].
    if isinstance(raw, (list, tuple)):
        parts = raw[0] if raw and isinstance(raw[0], (list, tuple)) else raw
        try:
            nums = [int(p) for p in parts if p is not None]
        except (TypeError, ValueError):
            return ParsedDate(None, _raw_text(raw), None, provenance, STATUS_INVALID)
        if not nums:
            return unknown(raw, provenance=provenance)
        return _from_parts(nums, _raw_text(raw), provenance)

    if isinstance(raw, (int, float)):
        # A unix timestamp. Seconds, or milliseconds when implausibly large.
        ts = float(raw)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            value = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, ValueError, OSError):
            return ParsedDate(None, _raw_text(raw), None, provenance, STATUS_INVALID)
        return ParsedDate(value, _raw_text(raw), PREC_SECOND, provenance, STATUS_OK)

    text = str(raw).strip()
    raw_text = text[:200]

    # Coarse ISO forms first: they are exact matches and carry precision.
    m = _ISO_YEAR.match(text)
    if m:
        return _from_parts([int(m.group(1))], raw_text, provenance)
    m = _ISO_MONTH.match(text)
    if m:
        return _from_parts([int(m.group(1)), int(m.group(2))], raw_text, provenance)
    m = _ISO_DAY.match(text) or _COMPACT_DAY.match(text)
    if m:
        return _from_parts([int(m.group(1)), int(m.group(2)), int(m.group(3))], raw_text, provenance)

    # Caller-supplied explicit formats (provider documentation).
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        value, assumed = _aware(dt, assume_utc)
        if value is None:
            return ParsedDate(None, raw_text, None, provenance, STATUS_INVALID)
        prec = PREC_DAY if "%H" not in fmt and "%I" not in fmt else PREC_SECOND
        if prec == PREC_DAY:
            value = value.replace(hour=0, minute=0, second=0, microsecond=0)
        return ParsedDate(value, raw_text, prec, provenance, STATUS_OK, assumed)

    # ISO 8601 with time.
    iso = text.replace("Z", "+00:00").replace("z", "+00:00")
    if " " in iso and "T" not in iso and re.match(r"^\d{4}-\d{2}-\d{2} \d", iso):
        iso = iso.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        dt = None
    if dt is not None:
        value, assumed = _aware(dt, assume_utc)
        if value is None:
            return ParsedDate(None, raw_text, None, provenance, STATUS_INVALID)
        prec = PREC_SECOND if (dt.second or dt.microsecond or dt.hour or dt.minute) else PREC_SECOND
        # ``2026-09-30T00:00:00`` is an exact instant as written; precision
        # loss is only recorded for inputs that carried no time at all.
        return ParsedDate(value, raw_text, prec, provenance, STATUS_OK, assumed)

    # RFC 2822 (RSS).
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is not None:
        value, assumed = _aware(dt, assume_utc or True)
        # parsedate_to_datetime returns naive for "-0000"; RFC 2822 says
        # that means UTC with no local knowledge, so assuming UTC is correct.
        return ParsedDate(value, raw_text, PREC_SECOND, provenance, STATUS_OK, assumed)

    return ParsedDate(None, raw_text, None, provenance, STATUS_INVALID)


def _from_parts(nums: Sequence[int], raw_text: Optional[str], provenance: str) -> ParsedDate:
    try:
        if len(nums) == 1:
            return ParsedDate(datetime(nums[0], 1, 1, tzinfo=timezone.utc), raw_text, PREC_YEAR, provenance, STATUS_OK)
        if len(nums) == 2:
            return ParsedDate(datetime(nums[0], nums[1], 1, tzinfo=timezone.utc), raw_text, PREC_MONTH, provenance, STATUS_OK)
        return ParsedDate(datetime(nums[0], nums[1], nums[2], tzinfo=timezone.utc), raw_text, PREC_DAY, provenance, STATUS_OK)
    except ValueError:
        return ParsedDate(None, raw_text, None, provenance, STATUS_INVALID)


def representative_instant(parsed: ParsedDate) -> Optional[datetime]:
    """The one instant to store for a coarse date, documented as such: the
    start of the day, month or year in UTC. Consumers must read the
    precision column before treating it as a time."""
    return parsed.value


def best_of(*candidates: ParsedDate) -> ParsedDate:
    """The first known candidate, preferring exact over coarse when both are
    known and from a non-model source. Used by merge logic (work package 8):
    a valid date beats a missing one; a conflicting date is not overwritten
    silently, which is the caller's job to record."""
    known = [c for c in candidates if c.known]
    if not known:
        for c in candidates:
            if c.status == STATUS_INVALID:
                return c
        return candidates[0] if candidates else unknown()
    non_model = [c for c in known if c.provenance != PROV_MODEL]
    pool = non_model or known
    exact = [c for c in pool if c.exact]
    return exact[0] if exact else pool[0]


def midnight_utc(value: Optional[datetime]) -> bool:
    """True when a stored timestamp sits at exactly 00:00:00 UTC, the
    signature of a day-precision date stored as an instant."""
    if value is None:
        return False
    v = value.astimezone(timezone.utc) if value.tzinfo else value
    return v.hour == 0 and v.minute == 0 and v.second == 0 and v.microsecond == 0
