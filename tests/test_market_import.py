"""Market registry import — the parsing rules the SOC Automation workbook forced.

Pure tests against a synthetic workbook with the same shape as the real one, so
a regression is caught without a database and without the customer file. Three
rules are pinned here because each one was a real defect: former-name aliases,
funding nulls, and two vendors sharing one LinkedIn page.

The monolith has no tenant column and no RLS, so unlike the SaaS suite there is
no isolation layer to test. Idempotency is exercised end-to-end against the
live schema by scripts/market_monitor_check.py.
"""

from __future__ import annotations

import io

import pytest

from app.services import market_import as mi

# ---------------------------------------------------------------------------
# A synthetic workbook with the shape of the real one
# ---------------------------------------------------------------------------

HEADERS = [
    "Vendor", "Category", "Sub-category", "In scope", "Country", "Founding Year",
    "Headcount", "Total Funding ($M)", "Funding status", "YTD Growth", "Website",
    "LinkedIn", "Notes", "Funding Notes (Analyst)",
]

ROWS = [
    # A genuine former name in parentheses.
    ["Variance (was Intrinsic)", "AI Security", "SOC Automation", "Yes",
     "United States", 2022, 16, 3.6, "Disclosed", 60,
     "https://withintrinsic.com/",
     "https://www.linkedin.com/company/intrinsicsafety?trk=public_post-text",
     "Trust & safety", None],
    # A parenthetical that is an ownership note, not a rename.
    ["Strike48 (A Devo company)", "AI Security", "SOC Automation", "Yes",
     "United States", 2021, 30, None, "Undisclosed", None,
     "https://www.strike48.com/", "https://www.linkedin.com/company/strike48/",
     None, None],
    # Bootstrapped: no amount, and that is the data.
    ["Imperum", "AI Security", "SOC Automation", "Yes", "Netherlands", 2021, 21,
     None, "Bootstrapped", -41.7, "https://www.imperum.io",
     "https://www.linkedin.com/company/imperumio/", None,
     "Bootstrapped (no funding round)"],
    # Two vendors sharing one LinkedIn page.
    ["Crogl", "Operations", "SOC Automation", "Yes", "United States", 2023, 40,
     20.0, "Disclosed", 10, "https://crogl.example",
     "https://www.linkedin.com/company/system-two-security/about/", None, None],
    ["System Two Security", "Operations", "SOC Automation", "Yes",
     "United States", 2022, 12, None, "Undisclosed", None,
     "https://systemtwo.example",
     "https://www.linkedin.com/company/system-two-security", None, None],
    # In scope but no LinkedIn at all.
    ["SOCAI", "AI Security", "SOC Automation", "Yes", "Israel", 2024, 8, None,
     "Undisclosed", None, "https://socai.example", None, None, None],
    # Out of scope: kept for provenance, never monitored.
    ["Edge Delta", "Operations", "Telemetry", "No", "United States", 2018, 200,
     63.0, "Disclosed", 5, "https://edgedelta.com/",
     "https://www.linkedin.com/company/edgedelta", None, None],
]

CHANGES = [
    ["Change type", "Vendor", "Field", "Old value", "New value", "Confidence",
     "Source", "Reason"],
    ["Identifier fix", "Crogl", "LinkedIn", "https://old", "https://new", "High",
     "site footer", "Source row carried the wrong URL."],
    ["Row removed", "Cyber Triage", "(entire row)", "present", "removed", "High",
     "shared site", "A product, not a company."],
]

ISSUES = [
    ["Severity", "Vendor", "Issue", "Detail"],
    ["Medium", "SOCAI", "Correction carries low confidence",
     "Headcount comes from a single aggregator."],
    ["Low", "Imperum", "Growth without a baseline", "No year-ago comparison."],
]


def _workbook() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = mi.SHEET_DATA
    ws.append(HEADERS)
    for row in ROWS:
        ws.append(row)
    ch = wb.create_sheet(mi.SHEET_CHANGES)
    for row in CHANGES:
        ch.append(row)
    iss = wb.create_sheet(mi.SHEET_ISSUES)
    for row in ISSUES:
        iss.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def parsed():
    return mi.parse_workbook(_workbook())


# ---------------------------------------------------------------------------
# Parsing rules
# ---------------------------------------------------------------------------

def test_counts_and_scope(parsed):
    assert len(parsed.vendors) == 7
    assert len(parsed.active) == 6
    excluded = [v for v in parsed.vendors if not v.in_scope]
    assert [v.display_name for v in excluded] == ["Edge Delta"]


def test_former_name_becomes_an_alias(parsed):
    v = next(v for v in parsed.vendors if v.slug == "variance")
    assert v.former_names == ["Intrinsic"]
    assert "Intrinsic" in v.aliases
    # The display name is kept exactly as the workbook wrote it.
    assert v.display_name == "Variance (was Intrinsic)"


def test_ownership_parenthetical_is_not_aliased(parsed):
    """'Strike48 (A Devo company)' must not gain the alias 'A Devo company'.

    A rule that turned every parenthetical into a searchable alias would make
    articles about the parent match the subsidiary.
    """
    v = next(v for v in parsed.vendors if v.slug == "strike48")
    assert v.former_names == []
    assert "A Devo company" not in v.aliases
    assert v.aliases == ["Strike48"]
    tasks = [t for t in parsed.review_tasks
             if t.vendor_slug == "strike48" and t.kind == "ambiguous_identity"]
    assert tasks, "an un-aliased parenthetical must raise a review task"


def test_undisclosed_funding_stays_unknown(parsed):
    """A missing amount under Undisclosed/Bootstrapped is never turned into 0."""
    for slug in ("strike48", "imperum", "socai"):
        v = next(v for v in parsed.vendors if v.slug == slug)
        assert v.total_funding_musd is None
        assert v.funding_status in ("Undisclosed", "Bootstrapped")


def test_shared_linkedin_page_raises_a_high_severity_task(parsed):
    """Two vendors on one page: the later row loses the identifier, loudly."""
    crogl = next(v for v in parsed.vendors if v.slug == "crogl")
    system_two = next(v for v in parsed.vendors if v.slug == "system-two-security")
    assert crogl.linkedin_url == "https://www.linkedin.com/company/system-two-security"
    assert system_two.linkedin_url is None
    high = [t for t in parsed.review_tasks if t.severity == "high"]
    assert len(high) == 1
    assert "same LinkedIn company page" in high[0].message


def test_missing_linkedin_on_an_in_scope_vendor_is_flagged(parsed):
    tasks = [t for t in parsed.review_tasks
             if t.vendor_slug == "socai" and t.field_name == "linkedin"]
    assert tasks and tasks[0].severity == "medium"


def test_issues_sheet_becomes_review_tasks(parsed):
    msgs = [t.message for t in parsed.review_tasks]
    assert any("single aggregator" in m for m in msgs)
    assert any("No year-ago comparison" in m for m in msgs)


def test_unmatched_change_records_are_kept(parsed):
    """The removed Cyber Triage row is why the count is 7 and not 8."""
    vendors = [r.get("vendor") for r in parsed.orphan_provenance]
    assert "Cyber Triage" in vendors
    assert "crogl" in parsed.provenance  # keyed by slug


def test_batch_id_is_derived_from_the_file(parsed):
    same = mi.parse_workbook(_workbook())
    assert same.batch_id == parsed.batch_id
    assert parsed.batch_id.startswith(f"{mi.MAPPING_VERSION}:")


def test_report_counts_match_the_registry(parsed):
    """The numbers an operator approves before anything is written."""
    report = mi.build_report(parsed)
    assert report["ok"] is True
    assert report["counts"]["rows"] == 7
    assert report["counts"]["active"] == 6
    # One vendor lost its LinkedIn identifier to the collision rule, and one
    # never had one — so four of six carry a usable company page.
    assert report["counts"]["linkedin"] == 4


def test_normalizers():
    assert mi.normalize_website("HTTP://WWW.Example.com/") == (
        "https://example.com", "example.com")
    assert mi.normalize_linkedin(
        "https://de.linkedin.com/company/Foo-Bar/?trk=x") == (
        "https://www.linkedin.com/company/foo-bar", "foo-bar")
    # A personal profile is not a company page.
    assert mi.normalize_linkedin("https://www.linkedin.com/in/someone") == (None, None)
    assert mi.former_name_from("was Intrinsic") == "Intrinsic"
    assert mi.former_name_from("formerly Acme") == "Acme"
    assert mi.former_name_from("A Devo company") is None


