"""Guardrails on the Market Monitor HTML report's own generated copy.

Regression test, not a style opinion: every pattern here caused a real
readability or honesty problem in an earlier version of this report and was
fixed by hand — a grammatically broken auto-generated sentence ("Based on 81
of 83 vendors have a founding year"), an unsupported causal claim ("hiring
says a vendor is still building"), or a term this report deliberately avoids
because it implies more certainty than the underlying data supports ("states
a fact"). If one of these strings reappears in a real render, someone
reintroduced the exact defect this file exists to catch.

Renders one real report rather than scanning the module's source text on
purpose: several of these phrases legitimately appear in this file's own
docstrings and comments, explaining the bug they fixed — a source-text scan
would flag its own explanation. Only the rendered HTML a reader actually
sees is checked.
"""

import re

import pytest

BANNED_PATTERNS = [
    r"[Bb]ased on \d+ of \d+ [^.]* have\b",
    r"rapidly evolving",
    r"dynamic landscape",
    r"increasingly competitive",
    r"shows? strong momentum",
    r"signals? strong traction",
    r"still building",
    r"started selling",
    r"states? a fact",
]


def _render_sample_report() -> str:
    from sqlalchemy import text as sqltext

    from app.database import get_database_instance
    from app.routes.market_monitor_routes import _load_market
    from app.services.market_report_html import build_market_report

    try:
        conn = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001 — no DB reachable, not a code failure
        pytest.skip(f"no database available for a report render: {exc}")

    try:
        market_id = conn.execute(
            sqltext("SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
        if market_id is None:
            pytest.skip("no market exists in this database to render a report for")
        market = _load_market(conn, market_id)
        return build_market_report(conn, market, days=30).decode("utf-8")
    finally:
        conn.close()


def test_report_has_no_banned_copy_patterns():
    html = _render_sample_report()
    hits = []
    for pattern in BANNED_PATTERNS:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            hits.append(f"{pattern!r} matched {match.group(0)!r}")
    assert not hits, "Banned report copy found in rendered output:\n" + "\n".join(hits)


def test_report_labels_every_coverage_chart_with_its_denominator():
    # Every _coverage() call renders a "X of Y ..." sentence right next to
    # the chart it describes — section 27's rule that a reader should never
    # have to hunt in the methodology text to find sparse coverage. A "mm-cover"
    # div with no digit in it would mean an empty or malformed coverage label.
    html = _render_sample_report()
    for div in re.findall(r'<div class="mm-cover[^"]*">([^<]*)</div>', html):
        assert re.search(r"\d", div), f"coverage label has no denominator: {div!r}"
