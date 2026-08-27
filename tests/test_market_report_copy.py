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
    r"dynamic market",
    r"increasingly competitive",
    r"shows? strong momentum",
    r"gaining momentum",
    r"signals? strong traction",
    r"strong traction",
    r"still building",
    r"started selling",
    r"states? a fact",
    # A headline count of vendors "with no signal" said we observed them all
    # and found nothing. The report now states an observation state per
    # vendor instead, and never a count of silence.
    r"[Vv]endors with no signal",
    r"no signal",
    # Crunchbase's proprietary scores are not market momentum.
    r"[Ff]unding and momentum",
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


# ---------------------------------------------------------------------------
# The mockup's parts, and the rules that keep them honest
# ---------------------------------------------------------------------------

def test_a_vendors_own_announcement_is_a_record_not_social_chatter():
    """The split is whose voice, not whether the item has social metadata.

    A vendor announcing a product on LinkedIn carries social metadata, so
    splitting on that filed the company's own statement under "Social" beside
    practitioner chatter — which said the announcement was somebody talking
    about it.
    """
    from app.services.market_report_html import _story_evidence

    html = _story_evidence({'supporting': [
        {'uri': 'https://linkedin.test/post', 'title': 'Acme ships',
         'source': 'linkedin', 'social': True, 'voice': 'owned'},
    ]})
    assert 'Social:' not in html
    assert "the company&#x27;s LinkedIn post" in html


def test_outside_discussion_is_separated_from_the_records():
    from app.services.market_report_html import _story_evidence

    html = _story_evidence({'supporting': [
        {'uri': 'https://sw.test/a', 'title': 'Acme ships',
         'source': 'securityweek.com', 'social': False, 'voice': 'independent'},
        {'uri': 'https://bsky.test/b', 'title': 'thoughts',
         'source': 'bluesky', 'social': True, 'voice': 'independent'},
    ]})
    assert '<strong>More:</strong>' in html and 'securityweek.com' in html
    assert '<strong>Social:</strong>' in html and 'Bluesky' in html


def test_two_links_from_one_platform_do_not_both_read_the_same():
    """Two links labelled "LinkedIn" tell a reader nothing about which to open."""
    from app.services.market_report_html import _story_evidence

    html = _story_evidence({'supporting': [
        {'uri': 'https://l.test/1', 'title': 'First announcement here',
         'source': 'linkedin', 'social': True, 'voice': 'owned'},
        {'uri': 'https://l.test/2', 'title': 'A second and different post',
         'source': 'linkedin', 'social': True, 'voice': 'owned'},
    ]})
    assert html.count("the company&#x27;s LinkedIn post") == 1
    assert 'A second and different post' in html


def test_records_held_without_a_link_are_admitted_not_hidden():
    from app.services.market_report_html import _story_evidence
    html = _story_evidence({'supporting': [], 'evidence_count': 3})
    assert '3 records held, none with a public link' in html
    assert _story_evidence({'supporting': [], 'evidence_count': 0}) == ''


def test_a_delta_against_nothing_is_not_a_percentage():
    """Dividing by a zero base produces a number that means nothing."""
    from app.services.market_report_html import _delta

    assert '%' not in _delta(5, 0)
    assert 'Up from none' in _delta(5, 0)
    # No earlier period at all: say so, and say since when, never a figure.
    assert '%' not in _delta(5, None)
    assert 'No earlier period' in _delta(5, None)
    assert '19 August 2026' in _delta(5, None, since='19 August 2026')
    assert 'Unchanged' in _delta(5, 5)
    assert '+100%' in _delta(2, 1)


def test_period_links_keep_the_signed_token():
    """A shared reader switching windows must not lose the token and 404."""
    from app.services.market_report_html import _relink

    out = _relink({'exp': 123, 'token': 'abc'}, days=7)
    assert 'exp=123' in out and 'token=abc' in out and 'days=7' in out
    # An operator with a session has no token, and the link must still work.
    assert _relink({}, days=90) == 'days=90'


# ---------------------------------------------------------------------------
# The working sits behind a disclosure, and stays reachable
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    from app.database import get_database_instance

    c = get_database_instance()._temp_get_connection()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture()
def market(conn):
    from sqlalchemy import text

    row = conn.execute(text(
        "SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip('no market in this database')
    return int(row)


def test_every_drawer_is_closed_and_none_is_left_open(conn, market):
    """Thirteen sections after a one-screen briefing made the briefing look
    like an introduction to a second document. They are collapsed now, and an
    unbalanced drawer would swallow everything after it.
    """
    from html.parser import HTMLParser
    from sqlalchemy import text
    from app.services.market_report_html import build_market_report

    row = conn.execute(text(
        "SELECT * FROM bw_markets WHERE id = :m"), {'m': market}).mappings().first()
    html = build_market_report(conn, dict(row), days=30).decode()

    void = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'source', 'track', 'wbr'}

    class Check(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.bad = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in void:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in void:
                return
            if not self.stack or self.stack[-1] != tag:
                self.bad.append(tag)
                if tag in self.stack:
                    del self.stack[self.stack.index(tag):]
                return
            self.stack.pop()

    check = Check()
    check.feed(html)
    assert not check.bad, f'mismatched tags: {check.bad[:3]}'
    assert not check.stack, f'never closed: {check.stack[:3]}'

    # Collapsed, not merely styled small. `<details open>` on any of these
    # would put the whole report back on one page.
    assert '<details class="mm-drawer" id="mm-analysis">' in html
    assert '<details class="mm-drawer" id="mm-registry">' in html
    assert '<details class="mm-drawer" id="mm-method">' in html
    assert 'mm-drawer" open' not in html and 'mm-drawer open' not in html


def test_the_nav_points_at_the_drawers_themselves(conn, market):
    """An anchor landing just outside a closed drawer scrolls to a shut door.

    The id has to be on the <details>, so the script walking up from the click
    target finds it and opens it.
    """
    from sqlalchemy import text
    from app.services.market_report_html import build_market_report

    row = conn.execute(text(
        "SELECT * FROM bw_markets WHERE id = :m"), {'m': market}).mappings().first()
    html = build_market_report(conn, dict(row), days=30).decode()

    for anchor in ('mm-analysis', 'mm-registry', 'mm-method'):
        assert f'href="#{anchor}"' in html, f'{anchor} is not in the nav'
        assert f'<details class="mm-drawer" id="{anchor}">' in html, (
            f'{anchor} must sit on the drawer, not on a marker beside it')


# ---------------------------------------------------------------------------
# Findings first: the order of the lead, and what is no longer on it
# ---------------------------------------------------------------------------

def test_the_lead_answers_before_it_shows_evidence(conn, market):
    """What changed, who changed, what it says, then the developments — and
    only then the drawers. A reader who stops after two screens has the
    answer; the charts are evidence, not the argument."""
    from sqlalchemy import text
    from app.services.market_report_html import build_market_report

    row = conn.execute(text(
        "SELECT * FROM bw_markets WHERE id = :m"), {'m': market}).mappings().first()
    html = build_market_report(conn, dict(row), days=30).decode()

    order = [html.index(marker) for marker in (
        '<h2>Executive assessment</h2>',
        '<h2>Vendors showing material change</h2>',
        '<h2>What this says about the market</h2>',
        '<h2>Material market developments</h2>',
        '<h2>Observed vendor activity</h2>',
        '<details class="mm-drawer" id="mm-analysis">',
    )]
    assert order == sorted(order), 'the lead is out of order'
    assert 'Funding and investor activity' in html
    assert 'collected records' in html and 'material development' in html
    # Every development names whose word it rests on.
    assert ('Vendor source only' in html or 'Also reported independently' in html
            or 'Reported by multiple independent sources' in html
            or 'No material development' in html)
    # The observation states, never a count of silence.
    assert 'monitored, no material change observed' in html
    assert 'with incomplete observation' in html or 'incomplete' in html
