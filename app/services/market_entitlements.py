"""Which vendors a viewer is allowed to see named.

A market report is shareable. ``/report.html`` opens three ways — a signed
link, a session, or the market's ``is_public`` flag — and until now all three
rendered the same file: every vendor in the roster, by name. A shared link to
the SOC Automation market disclosed all 84 companies to anyone holding the URL,
and because ``is_public`` was true, no token was needed at all.

The per-vendor ``bw_market_brands.is_public`` flag existed for exactly this, and
nothing read it. Zero read paths consulted it, and zero of the 84 vendors were
marked public — so the one control an operator had was both unset and ignored.

Three ideas make the fix safe rather than merely present.

**The server picks the set.** Never the browser. A restricted viewer is sent
only the rows it may see, so there is nothing in the payload, the page source,
an accessibility label or a CSV to recover the rest from.

**The set does not move.** It is derived from the market and the limit alone —
not from the period, not from a sort, not from the time of day. That is the
property that stops enumeration: a viewer who varies ``days`` twenty times sees
the same ten companies twenty times. Seeding it from a per-link value would be
worse, because two links would then expose two different tens and their union.

**It fails closed.** Filtering thirteen report sections by hand is a leak
waiting to happen — a vendor's name reaches the page through an event headline
or an article title, not only through a roster row. So the rendered output is
scanned for names the viewer is not entitled to, and if any survive, the report
is refused rather than served. A refusal is recoverable; a disclosure is not.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from sqlalchemy import text

logger = logging.getLogger(__name__)

# The public/shared default from the specification. An authenticated operator
# gets the whole market; everyone else gets this many vendor identities.
DEFAULT_PUBLIC_LIMIT = 10


def public_vendor_limit() -> int:
    try:
        return max(1, int(os.getenv("MARKET_PUBLIC_VENDOR_LIMIT",
                                    str(DEFAULT_PUBLIC_LIMIT))))
    except ValueError:
        return DEFAULT_PUBLIC_LIMIT


class Entitlement(NamedTuple):
    """How much of a market one viewer may see."""

    tier: str                      # 'full' or 'restricted'
    vendor_limit: Optional[int]    # None means every vendor
    reason: str                    # why, for the log and the page footer

    @property
    def restricted(self) -> bool:
        return self.vendor_limit is not None

    def describe(self, total: int) -> str:
        """What the page says about its own scope."""
        if not self.restricted:
            return f"All {total} monitored vendors."
        return (f"Top {self.vendor_limit} of {total} monitored vendors. "
                "The rest are not included in this view.")


FULL = Entitlement("full", None, "authenticated session")


def resolve(*, session: Any, signed_link: bool,
            market_is_public: bool) -> Entitlement:
    """What this request is entitled to.

    Everyone who gets through the door sees the whole market. Oliver's call on
    2026-09-22: the pages stop being a sample of themselves, and the thing we
    sell is MCP access, not the right to read a page without a blur over it.
    So the vendor cap, the blurred blocks, the scrubbed digits and the trial
    form are all gone — every one of them keys off a vendor limit, and there
    is no longer a reader who has one.

    Access itself is unchanged and is still decided before this is called: a
    valid signed link, a session, a subscriber's key, or a public market. A
    request with none of those is refused by the caller and never arrives
    here. This function answers "how much of it do they see", and the answer
    is now always "all of it".

    The machinery this used to drive is deliberately left in place —
    ``authorized_brand_ids``, ``withheld_names``, the fail-closed
    ``enforce_no_withheld`` guard. It costs nothing while no reader is
    limited, and restoring a tier is then a change to this function alone.
    """
    return FULL


def authorized_brand_ids(conn, market_id: int,
                         limit: Optional[int]) -> Optional[List[int]]:
    """The vendors a restricted viewer may see, deterministically.

    ``None`` means no restriction.

    Ranked by cumulative observed activity — earned coverage first, then the
    vendor's own posts, then open listings — with the canonical name as the
    final tie-break so the answer is stable and total. Cumulative rather than
    windowed on purpose: a 30-day count changes daily, and a set that churns
    daily leaks a different ten every day.

    Vendors an operator has explicitly marked public are always included. That
    flag is the one deliberate control over this and it should outrank a
    ranking nobody chose.
    """
    if limit is None:
        return None

    from app.services.market_corpus import earned_sql

    EARNED = earned_sql("a", "bac")
    rows = conn.execute(text(f"""
        WITH activity AS (
            SELECT mb.brand_id,
                   b.display_name,
                   mb.is_public,
                   -- Earned coverage only, so a vendor cannot rank into a
                   -- shared view on the strength of its own blog.
                   COALESCE((
                       SELECT COUNT(DISTINCT bac.article_uri)
                         FROM bw_article_categories bac
                         JOIN articles a ON a.uri = bac.article_uri
                        WHERE bac.brand_id = mb.brand_id
                          AND {EARNED}
                   ), 0) AS earned,
                   COALESCE((
                       SELECT COUNT(DISTINCT bac.article_uri)
                         FROM bw_article_categories bac
                         JOIN articles a ON a.uri = bac.article_uri
                        WHERE bac.brand_id = mb.brand_id
                          AND COALESCE(a.bias_source,'') = 'vendor:linkedin'
                   ), 0) AS owned,
                   COALESCE((
                       SELECT COUNT(DISTINCT s.provider_item_id)
                         FROM bw_vendor_snapshots s
                        WHERE s.brand_id = mb.brand_id
                          AND s.snapshot_type = 'job_posting'
                   ), 0) AS listings
              FROM bw_market_brands mb
              JOIN bw_brands b ON b.id = mb.brand_id
             WHERE mb.market_id = :m AND mb.role <> 'excluded'
        )
        SELECT brand_id
          FROM activity
         ORDER BY is_public DESC,
                  earned DESC, owned DESC, listings DESC,
                  display_name ASC
         LIMIT :lim
    """), {"m": market_id, "lim": limit}).fetchall()
    return [int(r[0]) for r in rows]


def vendor_names(conn, market_id: int,
                 brand_ids: Optional[Sequence[int]] = None) -> Dict[int, str]:
    """Every vendor name in a market, or just the named ones."""
    sql = """
        SELECT b.id, b.display_name
          FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
    """
    params: Dict[str, Any] = {"m": market_id}
    if brand_ids is not None:
        sql += " AND b.id = ANY(:ids)"
        params["ids"] = list(brand_ids)
    return {int(r[0]): r[1] for r in conn.execute(text(sql), params).fetchall()}


def withheld_names(conn, market_id: int,
                   allowed: Optional[Sequence[int]]) -> List[str]:
    """The vendor names this viewer must not see.

    What the backstop searches for. Returns an empty list for an unrestricted
    viewer, so the scan is a no-op rather than a special case at the call site.
    """
    if allowed is None:
        return []
    allowed_set = {int(b) for b in allowed}
    every = vendor_names(conn, market_id)
    return [name for bid, name in every.items()
            if bid not in allowed_set and name and name.strip()]


# ---------------------------------------------------------------------------
# Filtering payloads
# ---------------------------------------------------------------------------

# Keys that carry a vendor identity. A row holding any of these is dropped when
# its vendor is not authorized.
_ID_KEYS = ("brand_id", "vendor_id", "company_id")
_NAME_KEYS = ("vendor", "display_name", "company", "vendor_name")


def filter_rows(rows: Any, allowed: Optional[Sequence[int]],
                allowed_names: Optional[set] = None) -> Any:
    """Drop rows belonging to vendors this viewer may not see.

    Recursive, because the report's payloads nest — a per-vendor list inside a
    per-month bucket inside an analysis. Matches on id where a row has one and
    falls back to the name, since some aggregates carry only the label.

    A row with neither is kept: it is not about one vendor, and dropping
    everything unrecognised would empty the market-wide figures a restricted
    viewer is entitled to.
    """
    if allowed is None:
        return rows
    allowed_ids = {int(b) for b in allowed}

    if isinstance(rows, list):
        kept = []
        for row in rows:
            if isinstance(row, dict):
                ident = next((row[k] for k in _ID_KEYS
                              if isinstance(row.get(k), int)), None)
                if ident is not None and int(ident) not in allowed_ids:
                    continue
                if ident is None and allowed_names is not None:
                    name = next((row[k] for k in _NAME_KEYS
                                 if isinstance(row.get(k), str)), None)
                    if name is not None and name not in allowed_names:
                        continue
            kept.append(filter_rows(row, allowed, allowed_names))
        return kept
    if isinstance(rows, dict):
        return {k: filter_rows(v, allowed, allowed_names)
                for k, v in rows.items()}
    return rows


# What a masked row is called. Deliberately not a name-shaped string, so the
# backstop scan cannot match it and a reader cannot mistake it for a vendor.
WITHHELD_LABEL = "a vendor not shown in this view"


def mask_rows(rows: Any, allowed: Optional[Sequence[int]],
              label: str = WITHHELD_LABEL) -> Any:
    """Keep every row, but blank the names of vendors this viewer may not see.

    For aggregates. ``filter_rows`` drops rows, which changes the totals a
    finding is computed from: a shared view of ten vendors then reported the
    hiring concentration of those ten as though it were the market's, and
    printed "5 of 84 vendors" where the 5 counted the shown vendors and the 84
    counted everyone. This keeps the counts whole and withholds only the
    identity. The name keys become ``label`` and the row is marked
    ``withheld`` so a caller can collapse such rows into one line.
    """
    if allowed is None:
        return rows
    allowed_ids = {int(b) for b in allowed}

    if isinstance(rows, list):
        return [mask_rows(r, allowed, label) for r in rows]
    if isinstance(rows, dict):
        out = {k: mask_rows(v, allowed, label) for k, v in rows.items()}
        ident = next((rows[k] for k in _ID_KEYS
                      if isinstance(rows.get(k), int)), None)
        if ident is not None and int(ident) not in allowed_ids:
            for k in _NAME_KEYS:
                if k in out:
                    out[k] = label
            out["withheld"] = True
        return out
    return rows


def drop_text_mentioning(rows: Any, withheld: Sequence[str]) -> Any:
    """Drop items whose own words name a withheld vendor.

    Attribution is not enough. A news story about two companies is attributed
    to one of them, so filtering on the attributed vendor still prints the
    other company's name in the headline. This reads the text.

    Conservative by design: an item is dropped if any withheld name appears
    anywhere in it. A restricted view losing an article is a smaller cost than
    disclosing who else the market is watching.
    """
    if not withheld or not isinstance(rows, list):
        return rows
    # Case-insensitive. A vendor stored as "exaforce" appears in prose as
    # "Exaforce", and a case-sensitive backstop passed it straight through —
    # which made the whole check weaker than it looked.
    pattern = re.compile(
        "|".join(rf"(?<!\w){re.escape(n)}(?!\w)" for n in withheld),
        re.IGNORECASE)

    def _names_withheld(row: Any) -> bool:
        if isinstance(row, dict):
            blob = " ".join(str(v) for v in row.values()
                            if isinstance(v, (str, int, float)))
            if pattern.search(blob):
                return True
            # Nested structures: vendor lists as the corpus rows carry, and
            # dicts — an account row keeps its vendor in vendor_tag["org"]
            # and its profile text in account["summary"], both invisible to
            # the flat blob above (Torq, 4 Sep 2026).
            for value in row.values():
                if isinstance(value, list) and _any_withheld(value):
                    return True
                if isinstance(value, dict) and _names_withheld(value):
                    return True
            return False
        return bool(pattern.search(str(row)))

    def _any_withheld(items: List[Any]) -> bool:
        return any(_names_withheld(i) for i in items)

    return [r for r in rows if not _names_withheld(r)]


class DisclosureError(RuntimeError):
    """Rendered output names a vendor the viewer is not entitled to see."""


def enforce_no_withheld(rendered: str, withheld: Sequence[str], *,
                        context: str = "report") -> str:
    """The serve-safe tripwire for public pages: scrub instead of refuse.

    ``assert_no_withheld`` raising a 500 is the right shape for an
    entitlement API, but on the public site it turns any masking bug into
    an outage for every reader. Adding Torq to market 2 (4 Sep 2026) made a
    long-standing account blurb name a now-withheld vendor and took the
    shared report down for twelve minutes.

    So: the check still runs, and a hit is still treated as a bug — logged
    as an error with the context, so it gets found and fixed — but the page
    ships with each withheld name replaced by the withheld label. The
    replacement is the same word-boundary match the check uses, so what the
    check would have caught is exactly what gets scrubbed, and the result is
    re-checked before it leaves. If even the scrub cannot make the page
    clean, the original refusal stands.
    """
    if not withheld:
        return rendered
    try:
        assert_no_withheld(rendered, withheld, context=context)
        return rendered
    except DisclosureError as exc:
        logger.error("disclosure scrubbed from %s: %s "
                     "(a masking filter missed this name; fix the filter)",
                     context, exc)
    for name in withheld:
        rendered = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", WITHHELD_LABEL,
                          rendered, flags=re.IGNORECASE)
    assert_no_withheld(rendered, withheld, context=f"{context} (after scrub)")
    return rendered


def assert_no_withheld(rendered: str, withheld: Sequence[str], *,
                       context: str = "report") -> None:
    """Refuse to serve output that names a withheld vendor.

    The last line of defence, and the only one that does not depend on having
    remembered every section. A name reaches the page through an event
    headline, an article title or a chart label as readily as through a roster
    row, so the check is on the finished bytes.

    Matched on word boundaries: a vendor called "Joon" must not trip on the
    word "jooned" and, more to the point, must still trip on "Joon." at the end
    of a sentence.

    Raises rather than redacting. Redaction here would mean shipping a page
    assembled from data the viewer should never have had, and quietly patching
    the visible half of it.
    """
    if not withheld:
        return
    # One combined pass for the common, clean case. Scanning the finished
    # page once per withheld name cost ~0.7 s of every public render at 77
    # names; one alternation is one scan. The per-name pass below runs only
    # when something matched, which is already the error path.
    combined = re.compile(
        "|".join(rf"(?<!\w){re.escape(name)}(?!\w)" for name in withheld),
        re.IGNORECASE)
    if not combined.search(rendered):
        return
    found = sorted({name for name in withheld
                    if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", rendered,
                                 re.IGNORECASE)})
    if found:
        raise DisclosureError(
            f"{context} names {len(found)} vendor(s) the viewer is not "
            f"entitled to see: {', '.join(found[:5])}"
            + (" …" if len(found) > 5 else ""))


def log_access(*, market_id: int, entitlement: Entitlement,
               surface: str, viewer: Optional[str] = None) -> None:
    """Record who saw how much of which market.

    Full-market access is logged because the specification asks for it: an
    unrestricted view of a customer's competitive registry is worth being able
    to account for afterwards.
    """
    logger.info(
        "market %s %s access via %s (%s)%s",
        market_id, entitlement.tier, surface, entitlement.reason,
        f" by {viewer}" if viewer else "")
