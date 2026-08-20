"""Market registry import — spreadsheet in, reviewable proposal out.

Monolith port of the SaaS importer. The parsing half is identical because the
rules are about the spreadsheet, not the database. The write half differs:
there is no tenant column, no plan entitlement to preflight, and vendors get no
monitoring topic — Brand Watcher classifies the shared article corpus by brand
keywords, and collection is driven by keyword_groups.

Two phases, deliberately separate. ``validate`` parses the workbook and returns
everything it intends to do, keyed by a ``batch_id`` derived from the file's own
bytes; ``commit`` takes that batch_id back and writes, in one transaction. An
operator therefore sees the 83 rows, the aliases we inferred and the ones we
refused to infer, before anything touches ``bm_brands``.

Three rules the SOC Automation workbook taught us, all enforced here:

- A parenthetical is only a former name when it says so. ``Variance (was
  Intrinsic)`` yields the alias "Intrinsic". ``Strike48 (A Devo company)`` is an
  ownership statement and yields a review task, not an alias called
  "A Devo company".
- An empty funding cell is data. 44 of the 83 rows are ``Undisclosed`` or
  ``Bootstrapped`` and carry no amount; writing 0 would turn "we don't know"
  into "they raised nothing".
- Growth without a baseline is not growth. A YTD figure with no prior
  observation is stored as an assertion with its source, never as a rate we
  computed.

Text from the workbook is data. Nothing in a Notes or Issue cell is executed,
interpreted as an instruction, or passed to a model as one.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Bumped when the mapping rules below change, so a re-validated file that now
# parses differently gets a different batch_id and cannot be committed against
# a stale proposal.
MAPPING_VERSION = "1.0"

SHEET_DATA = "Corrected Data"
SHEET_CHANGES = "Changes"
SHEET_ISSUES = "Remaining issues"

# Header text (lowercased, punctuation-insensitive) → canonical field. Matching
# by header rather than column position means a reordered sheet is still read
# correctly instead of silently landing websites in the country column.
_HEADERS: dict[str, str] = {
    "vendor": "name",
    "company": "name",
    "category": "category",
    "subcategory": "sub_category",
    "in scope": "in_scope",
    "country": "hq_country",
    "founding year": "founded_year",
    "founded": "founded_year",
    "headcount": "headcount",
    "total funding m": "total_funding_musd",
    "total funding": "total_funding_musd",
    "funding status": "funding_status",
    "ytd growth": "employee_growth_ytd",
    "website": "website_url",
    "linkedin": "linkedin_url",
    "notes": "notes",
    "funding notes analyst": "funding_notes",
    "funding notes": "funding_notes",
}

_REQUIRED = ("name", "in_scope", "website_url")

# Only these introduce a former name. Anything else in parentheses is a
# qualifier we are not entitled to turn into a searchable alias.
_FORMER_NAME_PREFIXES = ("was ", "formerly ", "formerly known as ", "fka ", "ex ")

# LinkedIn company URLs arrive with tracking params, locale hosts and trailing
# slugs. The comparison key is the company slug alone.
_LINKEDIN_RE = re.compile(
    r"^https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|showcase)/([^/?#]+)",
    re.I,
)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return s[:100] or "vendor"


def normalize_website(url: str | None) -> tuple[Optional[str], Optional[str]]:
    """Return ``(canonical_url, domain)``. The supplied form is kept by the
    caller as ``display_value``; this is only the comparison key."""
    if not url:
        return None, None
    raw = url.strip()
    if not raw:
        return None, None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        p = urlparse(raw)
    except ValueError:
        return None, None
    host = (p.netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None, None
    path = (p.path or "").rstrip("/")
    canonical = urlunparse(("https", host, path, "", "", ""))
    return canonical, host


def normalize_linkedin(url: str | None) -> tuple[Optional[str], Optional[str]]:
    """Return ``(canonical_url, company_slug)`` or ``(None, None)``."""
    if not url:
        return None, None
    m = _LINKEDIN_RE.match(url.strip())
    if not m:
        return None, None
    slug = m.group(1).strip().lower().rstrip("/")
    if not slug:
        return None, None
    return f"https://www.linkedin.com/company/{slug}", slug


def split_parenthetical(name: str) -> tuple[str, Optional[str]]:
    """``"Variance (was Intrinsic)"`` → ``("Variance", "was Intrinsic")``."""
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", (name or "").strip())
    if not m:
        return (name or "").strip(), None
    return m.group(1).strip(), m.group(2).strip()


def former_name_from(parenthetical: str) -> Optional[str]:
    low = parenthetical.lower()
    for prefix in _FORMER_NAME_PREFIXES:
        if low.startswith(prefix):
            candidate = parenthetical[len(prefix):].strip(" .,")
            return candidate or None
    return None


def _norm_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", str(value or "").strip().lower()).strip()


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _as_int(value: Any) -> Optional[int]:
    s = _clean(value)
    if s is None:
        return None
    try:
        return int(float(s.replace(",", "")))
    except ValueError:
        return None


def _as_float(value: Any) -> Optional[float]:
    s = _clean(value)
    if s is None:
        return None
    try:
        return float(s.replace(",", "").replace("%", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Parsed shapes
# ---------------------------------------------------------------------------

@dataclass
class VendorRow:
    row_number: int
    display_name: str
    base_name: str
    slug: str
    aliases: list[str] = field(default_factory=list)
    former_names: list[str] = field(default_factory=list)
    category: Optional[str] = None
    sub_category: Optional[str] = None
    in_scope: bool = True
    hq_country: Optional[str] = None
    founded_year: Optional[int] = None
    headcount: Optional[int] = None
    total_funding_musd: Optional[float] = None
    funding_status: Optional[str] = None
    funding_notes: Optional[str] = None
    employee_growth_ytd: Optional[float] = None
    website_url: Optional[str] = None
    website_display: Optional[str] = None
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_slug: Optional[str] = None
    linkedin_display: Optional[str] = None
    notes: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def role(self) -> str:
        return "vendor" if self.in_scope else "excluded"


@dataclass
class ReviewTaskSpec:
    kind: str
    severity: str
    message: str
    field_name: Optional[str] = None
    vendor_slug: Optional[str] = None
    source_ref: dict = field(default_factory=dict)


@dataclass
class ParsedWorkbook:
    batch_id: str
    vendors: list[VendorRow]
    review_tasks: list[ReviewTaskSpec]
    provenance: dict[str, list[dict]]        # vendor slug → change records
    orphan_provenance: list[dict]            # changes naming no surviving row
    errors: list[str]
    warnings: list[str]

    @property
    def active(self) -> list[VendorRow]:
        return [v for v in self.vendors if v.in_scope]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _rows(ws) -> list[list[Any]]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _header_map(header: list[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for idx, cell in enumerate(header):
        canon = _HEADERS.get(_norm_header(cell))
        if canon and canon not in out:
            out[canon] = idx
    return out


def parse_workbook(data: bytes) -> ParsedWorkbook:
    """Parse the workbook into a proposal. Never touches the database."""
    import openpyxl

    errors: list[str] = []
    warnings: list[str] = []
    vendors: list[VendorRow] = []
    tasks: list[ReviewTaskSpec] = []
    provenance: dict[str, list[dict]] = {}
    orphans: list[dict] = []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — any parse failure is a user error
        return ParsedWorkbook(
            batch_id="", vendors=[], review_tasks=[], provenance={},
            orphan_provenance=[],
            errors=[f"Could not read the workbook: {type(exc).__name__}: {exc}"],
            warnings=[],
        )

    if SHEET_DATA not in wb.sheetnames:
        errors.append(
            f"Sheet '{SHEET_DATA}' not found. Sheets present: "
            f"{', '.join(wb.sheetnames)}"
        )
        return ParsedWorkbook("", [], [], {}, [], errors, warnings)

    grid = _rows(wb[SHEET_DATA])
    if len(grid) < 2:
        errors.append(f"Sheet '{SHEET_DATA}' has no data rows.")
        return ParsedWorkbook("", [], [], {}, [], errors, warnings)

    cols = _header_map(grid[0])
    missing = [f for f in _REQUIRED if f not in cols]
    if missing:
        errors.append(
            "Required columns missing from '"
            f"{SHEET_DATA}': {', '.join(missing)}. Headers found: "
            + ", ".join(str(h) for h in grid[0] if h)
        )
        return ParsedWorkbook("", [], [], {}, [], errors, warnings)

    def cell(row: list[Any], name: str) -> Any:
        idx = cols.get(name)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    seen_slugs: dict[str, int] = {}
    for offset, row in enumerate(grid[1:], start=2):
        raw_name = _clean(cell(row, "name"))
        if not raw_name:
            continue

        base_name, paren = split_parenthetical(raw_name)
        aliases: list[str] = []
        former: list[str] = []
        row_warnings: list[str] = []
        if paren:
            fn = former_name_from(paren)
            if fn:
                former.append(fn)
                aliases.append(fn)
            else:
                # Not a rename — an ownership or status note. Turning it into a
                # searchable alias would make every article about the parent
                # match the subsidiary.
                row_warnings.append(
                    f"Parenthetical '{paren}' is not a former name; not aliased."
                )
                tasks.append(ReviewTaskSpec(
                    kind="ambiguous_identity",
                    severity="low",
                    field_name="name",
                    message=(
                        f"'{raw_name}' carries the parenthetical '{paren}', which "
                        "does not read as a former name. It was not added as an "
                        "alias. Confirm whether it should be one."
                    ),
                    vendor_slug=slugify(base_name),
                    source_ref={"sheet": SHEET_DATA, "row": offset},
                ))
        if base_name != raw_name:
            aliases.append(base_name)

        slug = slugify(base_name)
        if slug in seen_slugs:
            row_warnings.append(
                f"Slug '{slug}' already used by row {seen_slugs[slug]}."
            )
            tasks.append(ReviewTaskSpec(
                kind="ambiguous_identity", severity="medium", field_name="name",
                message=(
                    f"Row {offset} ('{raw_name}') produces the same identifier as "
                    f"row {seen_slugs[slug]}. Only the first was imported."
                ),
                vendor_slug=slug,
                source_ref={"sheet": SHEET_DATA, "row": offset},
            ))
            continue
        seen_slugs[slug] = offset

        in_scope_raw = (_clean(cell(row, "in_scope")) or "yes").strip().lower()
        in_scope = in_scope_raw in ("yes", "y", "true", "1")

        website_display = _clean(cell(row, "website_url"))
        website_url, domain = normalize_website(website_display)
        if website_display and not website_url:
            row_warnings.append(f"Website '{website_display}' is not a usable URL.")
            tasks.append(ReviewTaskSpec(
                kind="data_quality", severity="medium", field_name="website",
                message=f"'{raw_name}': website '{website_display}' could not be parsed.",
                vendor_slug=slug, source_ref={"sheet": SHEET_DATA, "row": offset},
            ))

        linkedin_display = _clean(cell(row, "linkedin_url"))
        linkedin_url, linkedin_slug = normalize_linkedin(linkedin_display)
        if linkedin_display and not linkedin_url:
            row_warnings.append(
                f"LinkedIn '{linkedin_display}' is not a company URL."
            )
            tasks.append(ReviewTaskSpec(
                kind="data_quality", severity="medium", field_name="linkedin",
                message=(
                    f"'{raw_name}': LinkedIn URL '{linkedin_display}' is not a "
                    "recognisable company page."
                ),
                vendor_slug=slug, source_ref={"sheet": SHEET_DATA, "row": offset},
            ))
        if in_scope and not linkedin_display:
            tasks.append(ReviewTaskSpec(
                kind="data_quality", severity="medium", field_name="linkedin",
                message=(
                    f"'{raw_name}' is in scope but has no LinkedIn company URL, so "
                    "profile and post collection cannot run for it."
                ),
                vendor_slug=slug, source_ref={"sheet": SHEET_DATA, "row": offset},
            ))

        funding_status = _clean(cell(row, "funding_status"))
        total_funding = _as_float(cell(row, "total_funding_musd"))
        # Undisclosed and Bootstrapped are states, not zeros. Only flag the
        # contradiction: a row that claims a disclosed round but names no amount.
        if funding_status and funding_status.lower() == "disclosed" and total_funding is None:
            tasks.append(ReviewTaskSpec(
                kind="data_quality", severity="low", field_name="total_funding",
                message=(
                    f"'{raw_name}' is marked Disclosed but carries no funding amount."
                ),
                vendor_slug=slug, source_ref={"sheet": SHEET_DATA, "row": offset},
            ))

        vendors.append(VendorRow(
            row_number=offset,
            display_name=raw_name,
            base_name=base_name,
            slug=slug,
            aliases=[a for a in dict.fromkeys(aliases) if a and a != raw_name],
            former_names=former,
            category=_clean(cell(row, "category")),
            sub_category=_clean(cell(row, "sub_category")),
            in_scope=in_scope,
            hq_country=_clean(cell(row, "hq_country")),
            founded_year=_as_int(cell(row, "founded_year")),
            headcount=_as_int(cell(row, "headcount")),
            total_funding_musd=total_funding,
            funding_status=funding_status,
            funding_notes=_clean(cell(row, "funding_notes")),
            employee_growth_ytd=_as_float(cell(row, "employee_growth_ytd")),
            website_url=website_url,
            website_display=website_display,
            domain=domain,
            linkedin_url=linkedin_url,
            linkedin_slug=linkedin_slug,
            linkedin_display=linkedin_display,
            notes=_clean(cell(row, "notes")),
            warnings=row_warnings,
        ))

    # ── Cross-vendor identifier collisions ──────────────────────────────────
    # Two vendors resolving to one LinkedIn page or one domain is a merge the
    # registry has not made yet — the workbook's own Changes tab records
    # exactly this for Cyber Triage and Sleuth Kit Labs. Left undetected, the
    # second vendor silently loses its identifier and every post from that page
    # is attributed to the first. Keep the earlier row's claim, strip the
    # later one, and make a person decide.
    for attr, kind_label in (
        ("linkedin_url", "LinkedIn company page"),
        ("website_url", "website"),
        ("domain", "domain"),
    ):
        groups: dict[str, list[VendorRow]] = {}
        for v in vendors:
            value = getattr(v, attr)
            if value:
                groups.setdefault(value, []).append(v)
        for value, sharing in groups.items():
            if len(sharing) < 2:
                continue
            keeper, losers = sharing[0], sharing[1:]
            names = ", ".join(f"'{s.display_name}' (row {s.row_number})" for s in sharing)
            for loser in losers:
                setattr(loser, attr, None)
                if attr == "linkedin_url":
                    loser.linkedin_slug = None
                loser.warnings.append(
                    f"Shares a {kind_label} with '{keeper.display_name}'; "
                    "identifier not assigned."
                )
                tasks.append(ReviewTaskSpec(
                    kind="ambiguous_identity",
                    severity="high",
                    field_name=attr,
                    message=(
                        f"{names} all resolve to the same {kind_label} "
                        f"({value}). It was assigned to '{keeper.display_name}' "
                        "only. Decide whether these are one company, or correct "
                        "the identifier."
                    ),
                    vendor_slug=loser.slug,
                    source_ref={"sheet": SHEET_DATA, "row": loser.row_number,
                                "shared_value": value,
                                "rows": [s.row_number for s in sharing]},
                ))

    # ── Changes tab → provenance ────────────────────────────────────────────
    by_name = {v.display_name.lower(): v.slug for v in vendors}
    by_name.update({v.base_name.lower(): v.slug for v in vendors})
    if SHEET_CHANGES in wb.sheetnames:
        cgrid = _rows(wb[SHEET_CHANGES])
        if cgrid:
            chdr = [_norm_header(h) for h in cgrid[0]]
            for offset, row in enumerate(cgrid[1:], start=2):
                rec = {
                    chdr[i]: _clean(row[i])
                    for i in range(min(len(chdr), len(row)))
                    if chdr[i]
                }
                if not any(rec.values()):
                    continue
                rec["_row"] = offset
                vendor_name = (rec.get("vendor") or "").lower()
                slug = by_name.get(vendor_name)
                if slug:
                    provenance.setdefault(slug, []).append(rec)
                else:
                    # e.g. the removed Cyber Triage row — real history, no
                    # surviving vendor to hang it on.
                    orphans.append(rec)

    # ── Remaining issues tab → review tasks ─────────────────────────────────
    if SHEET_ISSUES in wb.sheetnames:
        igrid = _rows(wb[SHEET_ISSUES])
        if igrid:
            ihdr = [_norm_header(h) for h in igrid[0]]
            idx = {name: i for i, name in enumerate(ihdr) if name}
            for offset, row in enumerate(igrid[1:], start=2):
                def get(name: str) -> Optional[str]:
                    i = idx.get(name)
                    return _clean(row[i]) if i is not None and i < len(row) else None

                issue = get("issue")
                if not issue:
                    continue
                severity = (get("severity") or "low").strip().lower()
                if severity not in ("low", "medium", "high"):
                    severity = "low"
                detail = get("detail")
                vendor_name = (get("vendor") or "").lower()
                tasks.append(ReviewTaskSpec(
                    kind="data_quality",
                    severity=severity,
                    field_name=None,
                    message=f"{issue}. {detail}" if detail else issue,
                    vendor_slug=by_name.get(vendor_name),
                    source_ref={
                        "sheet": SHEET_ISSUES,
                        "row": offset,
                        "vendor": get("vendor"),
                    },
                ))

    wb.close()

    if not vendors:
        errors.append("No vendor rows found.")

    digest = hashlib.sha256(data).hexdigest()[:32]
    batch_id = f"{MAPPING_VERSION}:{digest}"
    return ParsedWorkbook(
        batch_id=batch_id,
        vendors=vendors,
        review_tasks=tasks,
        provenance=provenance,
        orphan_provenance=orphans,
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(parsed: ParsedWorkbook) -> dict[str, Any]:
    """The proposal an operator approves. Deterministic for a given file.

    No entitlement preflight: this deployment serves one customer, so there is
    no plan cap on how many vendors a market may hold.
    """
    active = parsed.active
    errors = list(parsed.errors)

    severities = {"high": 0, "medium": 0, "low": 0}
    for t in parsed.review_tasks:
        severities[t.severity] = severities.get(t.severity, 0) + 1

    return {
        "batch_id": parsed.batch_id,
        "ok": not errors,
        "errors": errors,
        "warnings": parsed.warnings,
        "counts": {
            "rows": len(parsed.vendors),
            "active": len(active),
            "excluded": len(parsed.vendors) - len(active),
            "websites": sum(1 for v in active if v.website_url),
            "linkedin": sum(1 for v in active if v.linkedin_url),
            "aliases": sum(len(v.aliases) for v in parsed.vendors),
            "review_tasks": len(parsed.review_tasks),
            "review_tasks_by_severity": severities,
            "provenance_records": sum(len(v) for v in parsed.provenance.values()),
            "provenance_unmatched": len(parsed.orphan_provenance),
        },
        "vendors": [
            {
                "row": v.row_number,
                "display_name": v.display_name,
                "slug": v.slug,
                "role": v.role,
                "aliases": v.aliases,
                "former_names": v.former_names,
                "domain": v.domain,
                "website_url": v.website_url,
                "linkedin_url": v.linkedin_url,
                "hq_country": v.hq_country,
                "founded_year": v.founded_year,
                "headcount": v.headcount,
                "funding_status": v.funding_status,
                "total_funding_musd": v.total_funding_musd,
                "employee_growth_ytd": v.employee_growth_ytd,
                "warnings": v.warnings,
            }
            for v in parsed.vendors
        ],
        "review_tasks": [
            {
                "kind": t.kind,
                "severity": t.severity,
                "field": t.field_name,
                "vendor": t.vendor_slug,
                "message": t.message,
                "source": t.source_ref,
            }
            for t in parsed.review_tasks
        ],
    }


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------
#
# Synchronous, against the monolith's connection facade. Callers in async
# routes must wrap this in ``asyncio.to_thread`` — an 83-row import held on the
# event loop blocks every other request in the process.


def _upsert_identifier(
    conn, *, brand_id: int, kind: str, normalized: str,
    display: str | None, external_id: str | None, provenance: dict,
) -> None:
    """Insert unless an identical live identifier already exists.

    The partial unique index covers ``valid_to IS NULL``, so a superseded
    identifier keeps its history while only one value per kind stays live. A
    live value already claimed by a *different* vendor is left alone — the
    parser has already filed a review task naming both.
    """
    conn.execute(text("""
        INSERT INTO bw_vendor_identifiers
            (brand_id, kind, normalized_value, display_value, external_id,
             provenance)
        SELECT :b, CAST(:k AS VARCHAR), CAST(:n AS TEXT), :d, :e,
               CAST(:p AS JSONB)
        WHERE NOT EXISTS (
            SELECT 1 FROM bw_vendor_identifiers
            WHERE kind = CAST(:k AS VARCHAR)
              AND normalized_value = CAST(:n AS TEXT)
              AND valid_to IS NULL
        )
    """), {"b": brand_id, "k": kind, "n": normalized, "d": display,
           "e": external_id, "p": json.dumps(provenance)})


def commit_import(conn, *, market_id: int, parsed: ParsedWorkbook) -> dict[str, Any]:
    """Write the proposal. Caller owns the transaction — this never commits.

    Idempotent: re-running the same workbook updates in place and creates no
    duplicate brand, identifier, snapshot or review task.
    """
    created = updated = adopted = 0
    identifiers = snapshots = 0
    conflicts: list[str] = []
    slug_to_brand: dict[str, int] = {}

    for v in parsed.vendors:
        keywords = list(dict.fromkeys(
            k for k in ([v.base_name] + list(v.aliases)) if k
        ))

        existing = conn.execute(
            text("SELECT id FROM bw_brands WHERE name = :n"), {"n": v.slug},
        ).scalar()

        if existing:
            member_of = [
                r[0] for r in conn.execute(
                    text("SELECT market_id FROM bw_market_brands WHERE brand_id = :b"),
                    {"b": existing},
                ).fetchall()
            ]
            other = [m for m in member_of if m != market_id]
            if other:
                # Another market already owns this brand. Adopting it would
                # rewrite that market's keywords underneath it.
                conflicts.append(
                    f"'{v.display_name}' matches an existing brand already in "
                    f"market {other[0]}; left untouched."
                )
                continue
            conn.execute(text("""
                UPDATE bw_brands
                SET display_name = :dn, brand_keywords = CAST(:kw AS JSONB),
                    updated_at = NOW()
                WHERE id = :id
            """), {"dn": v.display_name, "kw": json.dumps(keywords), "id": existing})
            brand_id = existing
            if member_of:
                updated += 1
            else:
                # An existing Brand Watcher brand pulled into a market. Worth
                # counting separately: somebody configured it by hand and the
                # import just took ownership of its keywords.
                adopted += 1
        else:
            brand_id = conn.execute(text("""
                INSERT INTO bw_brands
                    (name, display_name, description, brand_keywords, enabled)
                VALUES (:n, :dn, :descr, CAST(:kw AS JSONB), :en)
                RETURNING id
            """), {"n": v.slug, "dn": v.display_name, "descr": v.notes,
                   "kw": json.dumps(keywords), "en": v.in_scope}).scalar()
            created += 1

        slug_to_brand[v.slug] = brand_id

        baseline = {
            "import_batch_id": parsed.batch_id,
            "source_row": v.row_number,
            "taxonomy": {"category": v.category, "sub_category": v.sub_category},
            "hq_country": v.hq_country,
            "founded_year": v.founded_year,
            # The three funding states are kept apart on purpose; a missing
            # amount under "Undisclosed" is not zero.
            "funding_baseline": {
                "status": v.funding_status,
                "total_musd": v.total_funding_musd,
                "notes": v.funding_notes,
            },
            # Duplicated into the snapshot below. The snapshot is the dated
            # observation; this block is the flat record the vendor filters and
            # the UI table read.
            "metrics": {
                "employee_count": v.headcount,
                "employee_growth_ytd": v.employee_growth_ytd,
            },
            "analyst_note": v.notes,
            "warnings": v.warnings,
            "provenance": parsed.provenance.get(v.slug, []),
        }
        conn.execute(text("""
            INSERT INTO bw_market_brands
                (market_id, brand_id, role, sort_order, baseline, collection_enabled)
            VALUES (:m, :b, :r, :o, CAST(:bl AS JSONB), :ce)
            ON CONFLICT (market_id, brand_id) DO UPDATE
                SET role = EXCLUDED.role,
                    sort_order = EXCLUDED.sort_order,
                    baseline = EXCLUDED.baseline,
                    updated_at = NOW()
                -- collection_enabled and is_public are deliberately not
                -- refreshed: an operator who narrowed the market to funded
                -- vendors should not have that undone by re-importing.
        """), {"m": market_id, "b": brand_id, "r": v.role, "o": v.row_number,
               "bl": json.dumps(baseline), "ce": v.in_scope})

        prov = {"source": "workbook", "batch_id": parsed.batch_id,
                "sheet": SHEET_DATA, "row": v.row_number}
        for kind, normalized, display, ext in (
            ("website_url", v.website_url, v.website_display, None),
            ("domain", v.domain, v.domain, None),
            ("linkedin_company_url", v.linkedin_url, v.linkedin_display, v.linkedin_slug),
        ):
            if not normalized:
                continue
            _upsert_identifier(conn, brand_id=brand_id, kind=kind,
                               normalized=normalized, display=display,
                               external_id=ext, provenance=prov)
            identifiers += 1
        for alias in v.aliases:
            _upsert_identifier(conn, brand_id=brand_id, kind="alias",
                               normalized=alias.lower(), display=alias,
                               external_id=None, provenance=prov)
            identifiers += 1
        for former in v.former_names:
            _upsert_identifier(conn, brand_id=brand_id, kind="former_name",
                               normalized=former.lower(), display=former,
                               external_id=None, provenance=prov)
            identifiers += 1

        # Baseline measurements, recorded as observations with a source and a
        # date rather than as live readings — the workbook is a point in time.
        metrics = {k: val for k, val in (
            ("employee_count", v.headcount),
            ("employee_growth_ytd", v.employee_growth_ytd),
            ("total_funding_musd", v.total_funding_musd),
        ) if val is not None}
        if metrics:
            payload = {
                "metrics": metrics,
                "funding_status": v.funding_status,
                "source": "workbook",
                "batch_id": parsed.batch_id,
                "row": v.row_number,
                # A growth figure with no prior observation is an assertion we
                # carry, not a rate we computed.
                "growth_has_baseline": False,
            }
            blob = json.dumps(payload, sort_keys=True)
            conn.execute(text("""
                INSERT INTO bw_vendor_snapshots
                    (market_id, brand_id, source, snapshot_type,
                     provider_item_id, observed_at, data, content_hash)
                VALUES (:m, :b, 'workbook', 'metric', :pid, NOW(),
                        CAST(:d AS JSONB), :h)
                ON CONFLICT (source, provider_item_id, content_hash) DO NOTHING
            """), {"m": market_id, "b": brand_id,
                   "pid": f"{parsed.batch_id}:{v.row_number}", "d": blob,
                   "h": hashlib.sha256(blob.encode()).hexdigest()})
            snapshots += 1

    tasks_written = 0
    for t in parsed.review_tasks:
        brand_id = slug_to_brand.get(t.vendor_slug) if t.vendor_slug else None
        conn.execute(text("""
            INSERT INTO bw_review_tasks
                (market_id, brand_id, kind, severity, field, message, source_ref)
            VALUES (:m, :b, :k, :s, :f, :msg, CAST(:ref AS JSONB))
            ON CONFLICT (market_id, kind, COALESCE(brand_id, 0),
                         COALESCE(field, ''), md5(message))
                DO UPDATE SET severity = EXCLUDED.severity,
                              source_ref = EXCLUDED.source_ref,
                              updated_at = NOW()
        """), {"m": market_id, "b": brand_id, "k": t.kind, "s": t.severity,
               "f": t.field_name, "msg": t.message,
               "ref": json.dumps(t.source_ref)})
        tasks_written += 1

    # Changes naming no surviving vendor still belong to the market's history —
    # the removed Cyber Triage row is why the count is 83 and not 84.
    conn.execute(text("""
        UPDATE bw_markets
        SET config = COALESCE(config, '{}'::jsonb) || CAST(:patch AS JSONB),
            updated_at = NOW()
        WHERE id = :m
    """), {"m": market_id, "patch": json.dumps({
        "last_import": {
            "batch_id": parsed.batch_id,
            "rows": len(parsed.vendors),
            "active": len(parsed.active),
        },
        "import_provenance_unmatched": parsed.orphan_provenance,
    })})

    return {
        "batch_id": parsed.batch_id,
        "brands_created": created,
        "brands_updated": updated,
        "brands_adopted": adopted,
        "identifiers": identifiers,
        "snapshots": snapshots,
        "review_tasks": tasks_written,
        "conflicts": conflicts,
    }
