"""Who may see which vendors named.

MM-19 and MM-20 from the Market Monitor specification. This is access control,
so the tests are written to fail if the enforcement is removed, not merely to
exercise it: each one constructs a restricted viewer and asserts on the finished
bytes, which is where a leak actually happens.

The bug being guarded is not hypothetical. ``/report.html`` opens three ways —
signed link, session, or the market's ``is_public`` flag — and all three rendered
the same file: every vendor in the roster by name. The SOC Automation market's
shared link disclosed all 84 companies, and because ``is_public`` was true it
needed no token at all. The per-vendor ``is_public`` column existed for exactly
this and no read path consulted it.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.services import market_entitlements as ent

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='the ranking query is Postgres')


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
    row = conn.execute(text(
        "SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip('no market in this database')
    return int(row)


# ---------------------------------------------------------------------------
# Who gets what
# ---------------------------------------------------------------------------

def test_a_session_sees_everything_and_a_shared_link_does_not():
    assert ent.resolve(session={'user': 'admin'}, signed_link=False,
                       market_is_public=True) == ent.FULL
    assert ent.FULL.vendor_limit is None
    assert ent.FULL.restricted is False

    for kwargs in ({'signed_link': True, 'market_is_public': False},
                   {'signed_link': False, 'market_is_public': True}):
        got = ent.resolve(session=None, **kwargs)
        assert got.restricted
        assert got.vendor_limit == ent.public_vendor_limit()


def test_a_signed_link_is_not_more_trusted_than_a_public_market():
    """Harder to guess is not the same as more entitled.

    Both recipients are outside the account, so both get the same set. Treating
    a signed link as privileged would mean anyone who was ever sent one had a
    standing full-market view.
    """
    signed = ent.resolve(session=None, signed_link=True, market_is_public=False)
    public = ent.resolve(session=None, signed_link=False, market_is_public=True)
    assert signed.vendor_limit == public.vendor_limit


def test_no_credential_gets_the_tightest_answer_not_the_widest():
    """A missed check upstream must not become full access.

    The routes refuse before calling this, so this branch should be
    unreachable — which is exactly why it must not default to `FULL`.
    """
    got = ent.resolve(session=None, signed_link=False, market_is_public=False)
    assert got.restricted
    assert got.vendor_limit == 1


# ---------------------------------------------------------------------------
# MM-19: the set does not move
# ---------------------------------------------------------------------------

def test_mm19_the_authorized_set_is_the_same_every_time(conn, market):
    """Enumeration by repetition is the attack this prevents.

    The set is derived from the market and the limit alone. A viewer who varies
    the period, the sort, or simply reloads gets the same ten identities, so
    twenty requests cannot accumulate more than ten names.
    """
    first = ent.authorized_brand_ids(conn, market, 10)
    assert first is not None and len(first) == 10
    for _ in range(5):
        assert ent.authorized_brand_ids(conn, market, 10) == first


def test_mm19_a_bigger_entitlement_is_a_superset_not_a_reshuffle(conn, market):
    """Top 25 must contain Top 10.

    If the two tiers ranked differently, an account holding both would see more
    than 25 identities between them.
    """
    ten = ent.authorized_brand_ids(conn, market, 10)
    twenty_five = ent.authorized_brand_ids(conn, market, 25)
    assert set(ten).issubset(set(twenty_five))


def test_the_limit_is_exact_and_ties_do_not_expand_it(conn, market):
    """Returning "the top 10 plus everyone tied with tenth" leaks."""
    for limit in (1, 5, 10, 25):
        got = ent.authorized_brand_ids(conn, market, limit)
        in_scope = conn.execute(text("""
            SELECT COUNT(*) FROM bw_market_brands
             WHERE market_id = :m AND role <> 'excluded'
        """), {'m': market}).scalar()
        assert len(got) == min(limit, in_scope), limit
        assert len(set(got)) == len(got), 'no duplicate identities'


def test_an_unrestricted_viewer_is_not_filtered(conn, market):
    assert ent.authorized_brand_ids(conn, market, None) is None
    assert ent.withheld_names(conn, market, None) == []


def test_a_vendor_an_operator_marked_public_is_always_included(conn, market):
    """The one deliberate control outranks a ranking nobody chose."""
    victim = conn.execute(text("""
        SELECT mb.brand_id FROM bw_market_brands mb
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
         ORDER BY mb.brand_id DESC LIMIT 1
    """), {'m': market}).scalar()
    assert victim is not None
    assert victim not in (ent.authorized_brand_ids(conn, market, 3) or []), (
        'pick a vendor that is not already in the top 3')

    conn.execute(text("""
        UPDATE bw_market_brands SET is_public = true
         WHERE market_id = :m AND brand_id = :b
    """), {'m': market, 'b': victim})
    assert victim in ent.authorized_brand_ids(conn, market, 3)


# ---------------------------------------------------------------------------
# MM-20: nothing withheld reaches the output
# ---------------------------------------------------------------------------

def test_mm20_the_report_names_only_authorized_vendors(conn, market):
    """The whole point, asserted on the rendered bytes.

    Not on the payload: a vendor's name reaches the page through an event
    headline or an article title as readily as through a roster row, and only
    the finished document shows whether it did.
    """
    from app.services.market_report_html import build_market_report

    row = conn.execute(text(
        "SELECT * FROM bw_markets WHERE id = :m"), {'m': market}).mappings().first()
    allowed = ent.authorized_brand_ids(conn, market, 10)
    withheld = ent.withheld_names(conn, market, allowed)
    assert withheld, 'this market must have vendors to withhold'

    html = build_market_report(conn, dict(row), days=30,
                               allowed_brand_ids=allowed).decode()

    leaked = [n for n in withheld if n in html]
    assert not leaked, f'{len(leaked)} withheld vendor(s) named: {leaked[:5]}'

    # And the authorized ones are actually present, or this passes vacuously.
    shown = ent.vendor_names(conn, market, allowed).values()
    assert any(n in html for n in shown), 'no authorized vendor appears either'


def test_mm20_the_report_says_what_it_is_not_showing(conn, market):
    """A truncated view that does not admit it reads as the whole market."""
    from app.services.market_report_html import build_market_report

    row = conn.execute(text(
        "SELECT * FROM bw_markets WHERE id = :m"), {'m': market}).mappings().first()
    allowed = ent.authorized_brand_ids(conn, market, 10)
    html = build_market_report(conn, dict(row), days=30,
                               allowed_brand_ids=allowed).decode()
    assert 'shared view' in html
    assert 'monitored vendors' in html


def test_the_backstop_refuses_rather_than_redacting():
    """Fail closed.

    Redacting would mean serving a page assembled from data the viewer should
    never have had, with the visible half quietly patched. A refusal is
    recoverable; a disclosure is not.
    """
    with pytest.raises(ent.DisclosureError) as caught:
        ent.assert_no_withheld('a page about Acme Corp', ['Acme Corp'])
    assert 'not entitled' in str(caught.value)

    # No withheld names is a no-op, not a special case at the call site.
    ent.assert_no_withheld('anything at all', [])


def test_the_backstop_matches_whole_words_only():
    """A name must trip on punctuation and not on a longer word.

    "Joon." at the end of a sentence has to be caught; "jooned" must not be.
    """
    ent.assert_no_withheld('the file was jooned yesterday', ['Joon'])
    for text_body in ('we spoke to Joon.', 'Joon, among others', '(Joon)'):
        with pytest.raises(ent.DisclosureError):
            ent.assert_no_withheld(text_body, ['Joon'])


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def test_rows_are_dropped_by_id_and_by_name():
    rows = [
        {'brand_id': 1, 'vendor': 'Allowed'},
        {'brand_id': 2, 'vendor': 'Withheld'},
        {'vendor': 'Allowed'},          # name only, no id
        {'vendor': 'Withheld'},
        {'note': 'market-wide figure'},  # about no vendor
    ]
    got = ent.filter_rows(rows, [1], {'Allowed'})
    assert got == [
        {'brand_id': 1, 'vendor': 'Allowed'},
        {'vendor': 'Allowed'},
        # Kept: a row about no particular vendor is a market-wide figure a
        # restricted viewer is entitled to.
        {'note': 'market-wide figure'},
    ]


def test_filtering_reaches_nested_payloads():
    """The report's payloads nest — per-vendor lists inside monthly buckets."""
    payload = {'by_month': [{'month': '2026-08',
                             'vendors': [{'brand_id': 1, 'vendor': 'A'},
                                         {'brand_id': 9, 'vendor': 'Z'}]}]}
    got = ent.filter_rows(payload, [1], {'A'})
    assert got['by_month'][0]['vendors'] == [{'brand_id': 1, 'vendor': 'A'}]


def test_an_article_about_two_companies_is_dropped_not_kept():
    """Attribution alone is not enough.

    A story naming two vendors is attributed to one. Filtering on attribution
    keeps it and prints the other company's name in the headline.
    """
    rows = [
        {'title': 'Acme raises a round', 'vendors': [{'vendor': 'Acme'}]},
        {'title': 'Acme partners with Withheld Inc',
         'vendors': [{'vendor': 'Acme'}]},
        {'title': 'A market-wide trend', 'vendors': []},
    ]
    got = ent.drop_text_mentioning(rows, ['Withheld Inc'])
    assert [r['title'] for r in got] == ['Acme raises a round',
                                         'A market-wide trend']
    # No withheld names is a no-op.
    assert ent.drop_text_mentioning(rows, []) == rows


def test_the_limit_is_configurable_and_defaults_to_ten(monkeypatch):
    monkeypatch.delenv('MARKET_PUBLIC_VENDOR_LIMIT', raising=False)
    assert ent.public_vendor_limit() == ent.DEFAULT_PUBLIC_LIMIT == 10
    monkeypatch.setenv('MARKET_PUBLIC_VENDOR_LIMIT', '25')
    assert ent.public_vendor_limit() == 25
    # A nonsense value falls back rather than opening the market.
    monkeypatch.setenv('MARKET_PUBLIC_VENDOR_LIMIT', 'lots')
    assert ent.public_vendor_limit() == ent.DEFAULT_PUBLIC_LIMIT
    monkeypatch.setenv('MARKET_PUBLIC_VENDOR_LIMIT', '0')
    assert ent.public_vendor_limit() == 1, 'never zero, which would mean no cap'


def test_the_scope_line_states_both_numbers():
    restricted = ent.Entitlement('restricted', 10, 'shared report link')
    assert 'Top 10 of 84' in restricted.describe(84)
    assert ent.FULL.describe(84) == 'All 84 monitored vendors.'


def test_mm20_the_feed_names_only_authorized_vendors(conn, market):
    """The other anonymous surface.

    ``feed.xml`` is deliberately open so a reader can subscribe without a
    session, and it disclosed 20 of this market's 84 vendors — through article
    titles, not through any roster. Items are dropped rather than the document
    refused, because failing closed here would leave every public market with a
    permanently broken feed.
    """
    from app.services import market_publish as mp

    row = conn.execute(text(
        "SELECT * FROM bw_markets WHERE id = :m"), {'m': market}).mappings().first()
    allowed = ent.authorized_brand_ids(conn, market, 10)
    withheld = ent.withheld_names(conn, market, allowed)

    xml = mp.build_feed(conn, dict(row), base_url='https://example.test',
                        limit=50, allowed_brand_ids=allowed).decode()
    leaked = [n for n in withheld if n in xml]
    assert not leaked, f'{len(leaked)} withheld vendor(s) in the feed: {leaked[:5]}'

    # Still a usable feed, not an empty one.
    assert '<rss' in xml and '</channel>' in xml

    # And an operator's feed is not truncated.
    full = mp.build_feed(conn, dict(row), base_url='https://example.test',
                         limit=50).decode()
    assert len(full) >= len(xml)


def test_the_two_anonymous_routes_are_the_only_ones(conn):
    """A new anonymous route must not silently skip the gate.

    Every other market route requires a session, so entitlement only has to be
    enforced in two places. This fails if a third appears, which is the moment
    somebody needs to remember to gate it.
    """
    import ast
    import pathlib

    src = pathlib.Path('app/routes/market_monitor_routes.py').read_text()
    tree = ast.parse(src)
    anonymous = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if 'verify_session_optional' not in ast.dump(node):
            continue
        anonymous.append(node.name)
    assert sorted(anonymous) == ['market_feed', 'market_report'], (
        f'anonymous market routes changed: {sorted(anonymous)} — each one needs '
        'an entitlement gate before it ships')


def test_the_backstop_is_case_insensitive():
    """A vendor stored lowercase appears capitalised in prose.

    "exaforce" is the registry name; the feed said "Exaforce". A case-sensitive
    check passed it through, which made every other guarantee here weaker than
    it read — the name was in the output and the assertion said it was not.
    """
    for body in ('Exaforce announces a product', 'EXAFORCE raises a round',
                 'exaforce did something'):
        with pytest.raises(ent.DisclosureError):
            ent.assert_no_withheld(body, ['exaforce'])

    rows = [{'title': 'Exaforce announces ExaGo'}, {'title': 'Acme news'}]
    assert ent.drop_text_mentioning(rows, ['exaforce']) == [{'title': 'Acme news'}]
