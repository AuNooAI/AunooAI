"""Findings: market changes with evidence, not a feed of records.

MM-22 to MM-25 from the Market Monitor specification.

MM-22 — three reports of one event becoming one finding with the right source
count — is tested against a **constructed** fixture rather than live data, and
that is the honest way round: this market has no independently corroborated
event to read, because it has almost no independent coverage. See the module
docstring in app/services/market_findings for what that blocks. What is tested
here is the counting rule, which is the part that would be wrong silently.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services import market_findings as mf

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='the findings queries are Postgres jsonb and arrays')


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


def _a_brand(conn, market_id):
    bid = conn.execute(text("""
        SELECT brand_id FROM bw_market_brands
         WHERE market_id = :m AND role <> 'excluded' ORDER BY brand_id LIMIT 1
    """), {'m': market_id}).scalar()
    if bid is None:
        pytest.skip('no vendors')
    return int(bid)


def _make_event(conn, brand_id, *, event_type='funding_round',
                occurred_at=None, precision='day', sources=(),
                title='Acme raises a Series B'):
    """One event with a chosen set of evidence sources."""
    eid = conn.execute(text("""
        INSERT INTO bw_entity_events
            (event_type, title, description, occurred_at, date_precision,
             dedupe_hash, corroboration, status, confidence)
        VALUES (:t, :title, 'constructed for a test', :occ, :prec,
                :hash, 'uncorroborated', 'active', 0.8)
        RETURNING id
    """), {'t': event_type, 'title': title, 'occ': occurred_at,
           'prec': precision if occurred_at else 'unknown',
           'hash': hashlib.sha256(
               f'test-{title}-{occurred_at}-{event_type}'.encode()
           ).hexdigest()}).scalar()
    conn.execute(text("""
        INSERT INTO bw_entity_event_entities (event_id, brand_id, relation)
        VALUES (:e, :b, 'subject')
    """), {'e': eid, 'b': brand_id})
    for i, key in enumerate(sources):
        # Evidence must point at a real record: one reference is required
        # (ck_bw_entity_evidence_one_ref) and article_uri is a foreign key.
        # Both are the right constraints — a source with no record behind it is
        # an assertion — so the fixture lands an article first.
        uri = f'https://test.invalid/{eid}/{i}'
        conn.execute(text("""
            INSERT INTO articles (uri, title, summary, submission_date,
                                  news_source)
            VALUES (:uri, :title, 'constructed for a test', :now, :src)
            ON CONFLICT (uri) DO NOTHING
        """), {'uri': uri, 'title': f'{title} — report {i}',
               'now': datetime.now(timezone.utc).isoformat(),
               'src': key.split(':', 1)[-1]})
        conn.execute(text("""
            INSERT INTO bw_entity_event_evidence
                (event_id, evidence_type, relationship, independence_key,
                 article_uri, excerpt)
            VALUES (:e, 'article', 'originates', :k, :uri, :x)
        """), {'e': eid, 'k': key, 'uri': uri,
               'x': f'excerpt {i} from {key}'})
    from app.services import entity_events as ee
    ee.recompute_corroboration(conn, eid)
    return eid


# ---------------------------------------------------------------------------
# MM-22: several reports, one finding
# ---------------------------------------------------------------------------

def test_mm22_three_independent_reports_are_one_finding_with_three_sources(
        conn, market):
    """One event, three publishers: one finding, three evidence records.

    The count that matters is *distinct sources*, not evidence rows. Three
    records from one publisher are three rows and one source, and only the
    source count can make something corroborated.
    """
    brand_id = _a_brand(conn, market)
    eid = _make_event(conn, brand_id, occurred_at=datetime.now(timezone.utc),
                      sources=('domain:techcrunch.com', 'domain:reuters.com',
                               'domain:securityweek.com'))

    got = mf.findings(conn, market, days=30, page_size=500)
    mine = [f for f in got['data'] if f['finding_id'] == eid]
    assert len(mine) == 1, 'three reports must not become three findings'
    finding = mine[0]
    assert finding['evidence_count'] == 3
    assert finding['independent_source_count'] == 3
    assert finding['non_vendor_source_count'] == 3
    assert finding['status'] == 'corroborated'

    detail = mf.evidence(conn, market, eid)
    assert detail['meta']['evidence_count'] == 3
    assert detail['meta']['independent_source_count'] == 3
    assert all(r['voice'] == 'an independent publisher' for r in detail['data'])


def test_three_records_from_one_publisher_are_one_source(conn, market):
    """Syndication must not read as agreement."""
    brand_id = _a_brand(conn, market)
    eid = _make_event(conn, brand_id, title='Acme syndicated raise',
                      occurred_at=datetime.now(timezone.utc),
                      sources=('domain:wire.example',) * 3)
    got = mf.findings(conn, market, days=30, page_size=500)
    finding = next(f for f in got['data'] if f['finding_id'] == eid)
    assert finding['evidence_count'] == 3
    assert finding['independent_source_count'] == 1
    assert finding['status'] == 'watch', 'one publisher is not corroboration'


def test_a_vendors_own_channels_are_one_voice_and_never_corroborate(
        conn, market):
    """The blog and the LinkedIn post are the same company speaking.

    Dropzone AI's eleven blog posts were keyed by domain, so pairing one with
    the vendor's own LinkedIn post would have read as two sources agreeing.
    Manufactured consensus is the thing this system exists to detect, so
    producing it internally would be the worst available failure.
    """
    brand_id = _a_brand(conn, market)
    eid = _make_event(conn, brand_id, title='Acme announces itself twice',
                      occurred_at=datetime.now(timezone.utc),
                      sources=('owned:vendor:linkedin', 'owned:vendor:blog'))
    got = mf.findings(conn, market, days=30, page_size=500)
    finding = next(f for f in got['data'] if f['finding_id'] == eid)
    assert finding['non_vendor_source_count'] == 0
    assert finding['status'] == 'watch'

    detail = mf.evidence(conn, market, eid)
    assert all(r['voice'] == "the vendor's own channel" for r in detail['data'])
    assert detail['meta']['notes'], (
        'an all-owned finding has to say so')


def test_the_independence_key_treats_a_vendors_own_domain_as_owned(conn, market):
    """The specific gap: a vendor blog with no bias_source tag.

    ``bias_source`` was empty on Dropzone's blog rows, so the key fell through
    to the publisher domain and the vendor's own site counted as an independent
    publisher.
    """
    from app.services import entity_events as ee

    owned = ee.owned_domains(conn, market)
    assert owned, 'the market should have vendor domains on file'
    host, vendor = next(iter(owned.items()))

    key = ee.independence_key_for_article(None, f'https://www.{host}/blog/x',
                                          None, owned)
    assert key.startswith('owned:'), key
    # A third-party publisher stays independent.
    other = ee.independence_key_for_article(None, 'https://reuters.com/x', None,
                                            owned)
    assert other == 'domain:reuters.com'


# ---------------------------------------------------------------------------
# MM-24: no invented event date
# ---------------------------------------------------------------------------

def test_mm24_an_undated_finding_shows_no_event_date(conn, market):
    """``occurred_at`` stays null and the observation date is not put in its place.

    Filling the event date from the collection time would make every finding
    look like it happened the day we noticed it.
    """
    brand_id = _a_brand(conn, market)
    eid = _make_event(conn, brand_id, title='Acme did something undated',
                      occurred_at=None,
                      sources=('domain:example.com',))

    got = mf.findings(conn, market, days=3650, page_size=500)
    finding = next(f for f in got['data'] if f['finding_id'] == eid)
    assert finding['occurred_at'] is None
    assert finding['date_precision'] == 'unknown'
    # The first-observed date is present and separate, never promoted.
    assert finding['first_observed_at'] is not None
    assert finding['occurred_at'] != finding['first_observed_at']


def test_an_undated_finding_is_still_inside_the_window(conn, market):
    """Filtering on the event date alone would drop every undated finding.

    Which is the opposite of the intent: an undated change is exactly the kind
    a reader needs to see.
    """
    brand_id = _a_brand(conn, market)
    eid = _make_event(conn, brand_id, title='Acme undated but recent',
                      occurred_at=None, sources=('domain:example.com',))
    got = mf.findings(conn, market, days=30, page_size=500)
    assert any(f['finding_id'] == eid for f in got['data'])


# ---------------------------------------------------------------------------
# MM-25: the documented order
# ---------------------------------------------------------------------------

def test_mm25_recommended_order_follows_the_documented_tiers(conn, market):
    """Materiality, then evidence state, then date, then a stable id.

    Constructed so each tier is the only thing separating a pair.
    """
    brand_id = _a_brand(conn, market)
    now = datetime.now(timezone.utc)
    low = _make_event(conn, brand_id, event_type='hiring_spike',
                      title='Acme is hiring', occurred_at=now,
                      sources=('domain:a.example',))
    high_watch = _make_event(conn, brand_id, event_type='funding_round',
                             title='Acme raised money', occurred_at=now,
                             sources=('domain:b.example',))
    high_corrob = _make_event(conn, brand_id, event_type='acquisition',
                              title='Acme was acquired', occurred_at=now,
                              sources=('domain:c.example', 'domain:d.example'))

    order = [f['finding_id'] for f in
             mf.findings(conn, market, days=30, page_size=500,
                         sort='recommended')['data']]
    pos = {e: order.index(e) for e in (low, high_watch, high_corrob)}

    # Materiality beats evidence state, and evidence state breaks ties within it.
    assert pos[high_corrob] < pos[high_watch], 'corroborated outranks watch'
    assert pos[high_watch] < pos[low], 'high materiality outranks low'


def test_the_order_is_total_so_the_page_does_not_shuffle(conn, market):
    """Identical findings must not swap places between requests."""
    first = [f['finding_id'] for f in
             mf.findings(conn, market, days=30, page_size=500)['data']]
    for _ in range(3):
        assert [f['finding_id'] for f in
                mf.findings(conn, market, days=30, page_size=500)['data']] == first


def test_every_documented_sort_works_and_is_stable(conn, market):
    for sort in mf.SORTS:
        a = [f['finding_id'] for f in
             mf.findings(conn, market, days=30, page_size=500, sort=sort)['data']]
        b = [f['finding_id'] for f in
             mf.findings(conn, market, days=30, page_size=500, sort=sort)['data']]
        assert a == b, sort
        assert a, f'{sort} returned nothing'
    # An unknown sort falls back rather than erroring or ordering randomly.
    fallback = mf.findings(conn, market, days=30, page_size=500,
                           sort='nonsense')
    assert fallback['meta']['pagination']['sort'] == 'recommended'


# ---------------------------------------------------------------------------
# The executive section
# ---------------------------------------------------------------------------

def test_a_dismissed_finding_never_reaches_the_executive_section(conn, market):
    brand_id = _a_brand(conn, market)
    eid = _make_event(conn, brand_id, event_type='funding_round',
                      title='Acme raise, later rejected',
                      occurred_at=datetime.now(timezone.utc),
                      sources=('domain:e.example',))
    conn.execute(text("UPDATE bw_entity_events SET status='rejected' "
                      "WHERE id = :e"), {'e': eid})

    got = mf.findings(conn, market, days=30, page_size=500,
                      include_dismissed=True)
    finding = next(f for f in got['data'] if f['finding_id'] == eid)
    assert finding['status'] == 'dismissed'
    assert eid not in [f['finding_id'] for f in got['executive']]
    # And it is absent entirely unless asked for.
    assert eid not in [f['finding_id'] for f in
                       mf.findings(conn, market, days=30,
                                   page_size=500)['data']]


def test_a_low_materiality_watch_item_is_not_an_executive_finding(conn, market):
    """The most common record here, and it would crowd out everything else."""
    got = mf.findings(conn, market, days=30, page_size=500)
    for finding in got['executive']:
        assert not (finding['status'] == 'watch'
                    and finding['materiality'] == 'low')
    assert len(got['executive']) <= 5


def test_a_changed_web_page_is_not_a_medium_product_launch(conn, market):
    """The web-diff extractor files these as product_launch.

    "Andesite: news page changed" — twelve words different on a news index, with
    no date established — was ranking as a medium-materiality product launch in
    the executive summary. We know something changed and not what.
    """
    level, why = mf.materiality_of(
        'product_launch', corroboration='vendor_claim', vendor_count=1,
        attributes={'page_kind': 'news', 'changed_word_count': 12})
    assert level == 'low'
    assert 'page on the vendor' in why and '12 words' in why

    # A real launch with no page_kind is unaffected.
    level, _ = mf.materiality_of('product_launch',
                                 corroboration='vendor_claim', vendor_count=1)
    assert level == 'medium'


# ---------------------------------------------------------------------------
# Themes, materiality and status mapping
# ---------------------------------------------------------------------------

def test_every_event_type_in_the_database_lands_in_a_theme(conn):
    """An unmapped type must not disappear from the page."""
    types = [r[0] for r in conn.execute(text(
        "SELECT DISTINCT event_type FROM bw_entity_events")).fetchall()]
    for event_type in types:
        assert mf.theme_of(event_type) in mf.THEME_ORDER, event_type
    # An invented type falls back rather than vanishing.
    assert mf.theme_of('something_new') == mf.FALLBACK_THEME
    assert mf.theme_of(None) == mf.FALLBACK_THEME


def test_a_vendor_claim_is_a_watch_item_not_a_confirmed_finding():
    """A company announcing its own news is evidence of what it said."""
    assert mf.status_of('active', 'vendor_claim') == 'watch'
    assert mf.status_of('active', 'single_source') == 'watch'
    assert mf.status_of('active', 'uncorroborated') == 'watch'
    assert mf.status_of('active', 'corroborated') == 'corroborated'
    assert mf.status_of('active', 'primary_document') == 'confirmed'
    for dead in ('rejected', 'superseded'):
        assert mf.status_of(dead, 'corroborated') == 'dismissed'


def test_materiality_always_comes_with_its_reason():
    """The spec forbids an unexplained score, so the rule travels with it."""
    for event_type in ('funding_round', 'partnership', 'hiring_spike',
                       'something_unmapped'):
        level, why = mf.materiality_of(event_type, corroboration='vendor_claim',
                                       vendor_count=1)
        assert level in ('high', 'medium', 'low')
        assert why and len(why) > 8, (event_type, why)

    # Hiring is deliberately low: every growing company is always hiring.
    assert mf.materiality_of('hiring_spike', corroboration='vendor_claim',
                             vendor_count=1)[0] == 'low'
    # A change touching several monitored vendors is a market movement.
    assert mf.materiality_of('partnership', corroboration='vendor_claim',
                             vendor_count=3)[0] == 'high'


# ---------------------------------------------------------------------------
# MM-23 and the other degraded states
# ---------------------------------------------------------------------------

def test_mm23_evidence_collected_but_not_examined_is_not_no_findings(conn,
                                                                     market):
    """The distinction MM-23 is about.

    Saying "no findings" when the evidence has not been read is the same error
    as reporting a zero from a collector that never ran.
    """
    # Nothing examined, and no events in the window.
    conn.execute(text(
        "UPDATE bw_market_articles SET review_verdict = NULL "
        "WHERE market_id = :m"), {'m': market})
    conn.execute(text("""
        UPDATE bw_entity_events SET status = 'rejected'
         WHERE id IN (SELECT ee.event_id FROM bw_entity_event_entities ee
                       JOIN bw_market_brands mb ON mb.brand_id = ee.brand_id
                      WHERE mb.market_id = :m)
    """), {'m': market})

    got = mf.findings(conn, market, days=30)
    state = got['meta']['synthesis']
    assert got['meta']['pagination']['total'] == 0
    assert state['state'] == 'synthesis_pending', state
    assert state['evidence_items'] > 0
    assert 'not yet examined' in state['detail']


def test_a_failed_collector_is_not_an_empty_findings_page(conn, market):
    """Collection incomplete outranks every other empty state."""
    conn.execute(text("""
        UPDATE bw_entity_source_policies SET last_success_at = NULL
         WHERE source = 'linkedin_company_post' AND brand_id IN (
               SELECT brand_id FROM bw_market_brands WHERE market_id = :m)
    """), {'m': market})
    conn.execute(text("DELETE FROM bw_collection_runs WHERE market_id = :m "
                      "AND source = 'linkedin_company_post'"), {'m': market})

    got = mf.findings(conn, market, days=30)
    assert got['meta']['synthesis']['state'] == 'collection_incomplete'


def test_the_page_says_when_nothing_is_corroborated(conn, market):
    """Every event in this market rests on one source, and that gets said."""
    got = mf.findings(conn, market, days=30, page_size=500)
    if got['meta']['counts']['corroborated'] == 0 and got['data']:
        assert any('independently corroborated' in n
                   for n in got['meta']['notes'])


def test_the_metric_says_findings_are_not_an_activity_feed(conn, market):
    got = mf.findings(conn, market, days=30)
    limits = ' '.join(got['meta']['metric']['limitations']).lower()
    assert 'not a complete activity feed' in limits
    assert 'event date' in limits
    assert 'materiality' in limits


def test_filters_are_echoed_and_actually_applied(conn, market):
    got = mf.findings(conn, market, days=30, materiality='high',
                      page_size=500)
    assert got['meta']['applied_filters']['materiality'] == 'high'
    assert all(f['materiality'] == 'high' for f in got['data'])

    themed = mf.findings(conn, market, days=30,
                         theme='Hiring and headcount', page_size=500)
    assert all(f['theme'] == 'Hiring and headcount' for f in themed['data'])


def test_evidence_for_a_finding_outside_this_market_is_refused(conn, market):
    with pytest.raises(ValueError):
        mf.evidence(conn, market, 99999999)


def test_the_supporting_relationship_set_matches_the_canonical_one(conn):
    """Two counts of the same thing must use the same rule.

    ``entity_events.recompute_corroboration`` decides the corroboration field;
    this module counts sources for display. I first wrote the display side as
    ``relationship = 'supports'``, which excluded ``originates`` — 201 of 216
    evidence rows — so every finding showed zero sources beside a corroboration
    field that disagreed. The narrower version was wrong in two separate places
    before it was named once.
    """
    import inspect

    from app.services import entity_events as ee

    source = inspect.getsource(ee.recompute_corroboration)
    for relationship in mf.SUPPORTING:
        assert f"'{relationship}'" in source, (
            f"{relationship} is counted as supporting here but not by "
            "recompute_corroboration")
    assert 'contradicts' not in mf.SUPPORTING


def test_a_contradicting_record_does_not_support_a_finding(conn, market):
    brand_id = _a_brand(conn, market)
    eid = _make_event(conn, brand_id, title='Acme disputed raise',
                      occurred_at=datetime.now(timezone.utc),
                      sources=('domain:one.example',))
    uri = 'https://test.invalid/contra'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, submission_date, news_source)
        VALUES (:u, 'Denial', 'x', :now, 'two.example')
        ON CONFLICT (uri) DO NOTHING
    """), {'u': uri, 'now': datetime.now(timezone.utc).isoformat()})
    conn.execute(text("""
        INSERT INTO bw_entity_event_evidence
            (event_id, evidence_type, relationship, independence_key,
             article_uri, excerpt)
        VALUES (:e, 'article', 'contradicts', 'domain:two.example', :u, 'no')
    """), {'e': eid, 'u': uri})

    got = mf.findings(conn, market, days=30, page_size=500)
    finding = next(f for f in got['data'] if f['finding_id'] == eid)
    assert finding['independent_source_count'] == 1, 'the denial is not support'
    assert finding['has_contradiction'] is True


# ---------------------------------------------------------------------------
# Who the statement is about, not who made it (the self-reportable rule)
# ---------------------------------------------------------------------------

def test_a_vendor_is_the_record_for_its_own_product_launch():
    """A company shipping its own product needs nobody's confirmation.

    Treating that as a watch item asked Exaforce to corroborate Exaforce, and
    printed "no independent source" as though our evidence were short. It is
    not short — there is nobody else to ask.
    """
    assert mf.status_of('active', 'vendor_claim', event_type='product_launch',
                        vendor_voiced=True) == 'confirmed'
    assert mf.status_of('active', 'vendor_claim', event_type='leadership_change',
                        vendor_voiced=True) == 'confirmed'


def test_a_claim_about_somebody_else_stays_a_watch_item():
    """The other party in a customer win or a round has not spoken yet."""
    for kind in ('customer_win', 'partnership', 'funding_round', 'acquisition',
                 'layoff'):
        assert mf.status_of('active', 'vendor_claim', event_type=kind,
                            vendor_voiced=True) == 'watch', kind


def test_the_rule_needs_the_vendor_to_be_the_one_talking():
    """An unattributed single source is not a vendor announcement.

    Without this the rule would promote any lone source on a product-launch
    event, including a blog nobody has vouched for.
    """
    assert mf.status_of('active', 'vendor_claim', event_type='product_launch',
                        vendor_voiced=False) == 'watch'


def test_a_rejected_event_is_dismissed_whoever_said_it():
    assert mf.status_of('rejected', 'vendor_claim', event_type='product_launch',
                        vendor_voiced=True) == 'dismissed'


def test_vendor_announcements_do_not_bury_a_corroborated_finding(conn, market):
    """Ordering ranks outside interest above the status label.

    Once a self-announced launch became "confirmed", ranking on the status
    label alone floated every routine vendor post above a named contract that
    somebody else had reported. The evidence tier exists to surface outside
    interest, so it counts outside sources first.
    """
    brand_id = _a_brand(conn, market)
    now = datetime.now(timezone.utc)
    own = _make_event(conn, brand_id, event_type='product_launch',
                      title='Acme ships a thing', occurred_at=now,
                      sources=('owned:vendor:acme',))
    reported = _make_event(conn, brand_id, event_type='product_launch',
                           title='Acme feature reviewed elsewhere',
                           occurred_at=now - timedelta(days=1),
                           sources=('domain:one.example', 'domain:two.example'))

    got = mf.findings(conn, market, days=30, sort='recommended', page_size=500)
    order = [f['finding_id'] for f in got['data']]
    assert order.index(reported) < order.index(own), (
        'two outside sources must outrank a vendor announcing itself')
