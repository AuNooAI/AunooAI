"""Events and narratives — the claims that must not become facts by accident.

Two failure modes are pinned here. An event reported once and copied ten times
must not read as ten confirmations, and a company's own announcement must not
quietly become established fact because nobody looked at where it came from.
Then, for generated prose: a number that appears in the text and nowhere in the
evidence is the single most damaging thing this system can emit, because it is
the one a reader has no way to doubt.

The pure tests need no database. The rest run in a transaction that is always
rolled back.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services import entity_events, entity_narratives

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='events and narratives are exercised against PostgreSQL')

WHEN = datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Identity — pure
# ---------------------------------------------------------------------------

def test_the_same_event_reported_twice_has_one_fingerprint():
    """A retried callback and a second outlet are the same happening."""
    first = entity_events.fingerprint(
        event_type='funding_round', brand_ids=[10],
        attributes={'round': 'series_a'}, occurred_at=WHEN)
    second = entity_events.fingerprint(
        event_type='funding_round', brand_ids=[10],
        attributes={'round': 'series_a'},
        occurred_at=WHEN + timedelta(hours=6))
    assert first == second


def test_a_different_day_is_a_different_event():
    later = WHEN + timedelta(days=3)
    assert entity_events.fingerprint(
        event_type='funding_round', brand_ids=[10], occurred_at=WHEN
    ) != entity_events.fingerprint(
        event_type='funding_round', brand_ids=[10], occurred_at=later)


def test_subject_order_does_not_change_identity():
    """An acquisition described from either side is one acquisition."""
    assert entity_events.fingerprint(
        event_type='acquisition', brand_ids=[10, 11]
    ) == entity_events.fingerprint(
        event_type='acquisition', brand_ids=[11, 10])


def test_an_undated_event_buckets_as_unknown():
    assert entity_events.date_bucket(None) == 'unknown'
    assert entity_events.date_bucket(WHEN) == '2026-08-14'
    assert entity_events.date_bucket(WHEN, 'month') == '2026-08'


def test_syndicated_copies_share_a_source_key():
    """Ten outlets republishing one wire story are one voice, and the key is
    what makes that countable."""
    a = entity_events.independence_key_for_article('Reuters', 'https://reuters.com/a/1')
    b = entity_events.independence_key_for_article('Reuters', 'https://reuters.com/b/2')
    c = entity_events.independence_key_for_article('TechCrunch',
                                                   'https://techcrunch.com/x')
    assert a == b
    assert a != c


def test_a_companys_own_channels_are_one_voice():
    key = entity_events.independence_key_for_article(
        'linkedin', 'https://linkedin.com/posts/1', 'vendor:linkedin')
    assert key.startswith('owned:')


def test_self_reported_sources_are_marked_owned():
    """A job advert and a page on the company's own site are the company
    speaking, whichever platform delivered them."""
    assert entity_events.independence_key_for_source('linkedin_jobs').startswith('owned:')
    assert entity_events.independence_key_for_source('vendor_web').startswith('owned:')
    assert entity_events.independence_key_for_source('crunchbase_company').startswith('source:')


# ---------------------------------------------------------------------------
# Against the real schema
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    from app.database import get_database_instance

    db = get_database_instance()
    connection = db._temp_get_connection()
    if connection.execute(
            text("SELECT to_regclass('bw_entity_events')")).scalar() is None:
        connection.close()
        pytest.skip('ei_003 has not been applied to this database')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture()
def brand(conn):
    return conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-events', 'Pytest Events Co', '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()


@pytest.fixture()
def owned_article(conn):
    uri = 'pytest://events/owned-post'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url, bias_source)
        VALUES (:u, 'We raised a Series A', 'Our round.', 'linkedin',
                'https://linkedin.com/posts/1', 'vendor:linkedin')
    """), {'u': uri})
    return uri


@pytest.fixture()
def press_article(conn):
    uri = 'pytest://events/press'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url)
        VALUES (:u, 'Pytest Events Co raises Series A', 'Reported.',
                'TechCrunch', 'https://techcrunch.com/x')
    """), {'u': uri})
    return uri


def _round(conn, brand, evidence):
    return entity_events.record(
        conn, event_type='funding_round', title='Series A',
        description='A round.', brand_ids={brand: 'subject'},
        attributes={'round': 'series_a'}, occurred_at=WHEN,
        evidence=evidence)


def test_a_retry_merges_instead_of_duplicating(conn, brand, owned_article):
    """The same extraction run twice must not produce two events."""
    evidence = [{'evidence_type': 'article', 'article_uri': owned_article,
                 'relationship': 'originates',
                 'independence_key': 'owned:vendor:linkedin'}]
    first = _round(conn, brand, evidence)
    second = _round(conn, brand, evidence)

    assert first['created'] is True
    assert second['created'] is False
    assert first['event_id'] == second['event_id']

    count = conn.execute(text("""
        SELECT count(*) FROM bw_entity_events WHERE dedupe_hash = :h
    """), {'h': first['dedupe_hash']}).scalar()
    assert count == 1


def test_a_vendor_claim_stays_a_claim_until_somebody_else_says_it(
        conn, brand, owned_article, press_article):
    """The company announcing its own round is information, and it is not the
    same as independent confirmation."""
    claim = _round(conn, brand, [
        {'evidence_type': 'article', 'article_uri': owned_article,
         'relationship': 'originates',
         'independence_key': 'owned:vendor:linkedin'}])
    assert claim['corroboration'] == 'vendor_claim'

    # Independent coverage arrives; the event is the same event.
    confirmed = _round(conn, brand, [
        {'evidence_type': 'article', 'article_uri': press_article,
         'relationship': 'supports',
         'independence_key': 'domain:techcrunch.com'}])
    assert confirmed['event_id'] == claim['event_id']
    assert confirmed['corroboration'] == 'single_source'

    # And the original evidence is still attached, not replaced.
    evidence = entity_events.evidence_for_event(conn, claim['event_id'])
    assert {e['article_uri'] for e in evidence} == {owned_article, press_article}


def test_two_copies_of_one_wire_story_are_not_two_sources(conn, brand):
    """Counting evidence rows instead of distinct sources is how a press
    release comes to look widely confirmed."""
    result = entity_events.record(
        conn, event_type='partnership', title='A partnership',
        description='.', brand_ids={brand: 'subject'}, occurred_at=WHEN,
        evidence=[])
    for path in ('a', 'b', 'c'):
        conn.execute(text("""
            INSERT INTO articles (uri, title, news_source, url)
            VALUES (:u, 'Syndicated', 'Reuters', :url)
        """), {'u': f'pytest://wire/{path}', 'url': f'https://reuters.com/{path}'})
        entity_events.add_evidence(
            conn, result['event_id'], evidence_type='article',
            article_uri=f'pytest://wire/{path}', relationship='supports',
            independence_key='domain:reuters.com')

    state = entity_events.recompute_corroboration(conn, result['event_id'])
    assert state['independent_sources'] == 1
    assert state['corroboration'] == 'single_source'


def test_a_vendors_own_page_is_not_a_primary_document(conn, brand):
    """Only a filing or equivalent reaches the top rung. A company's press
    page is the company talking."""
    result = entity_events.record(
        conn, event_type='product_launch', title='A launch', description='.',
        brand_ids={brand: 'subject'}, occurred_at=WHEN,
        evidence=[{'evidence_type': 'observation', 'observation_id': None,
                   'relationship': 'originates',
                   'independence_key': 'owned:vendor_web'}]
        if False else [])
    conn.execute(text("""
        INSERT INTO articles (uri, title, news_source, url, bias_source)
        VALUES ('pytest://own/page', 'Our news', 'linkedin',
                'https://x.test/p', 'vendor:linkedin')
    """))
    entity_events.add_evidence(
        conn, result['event_id'], evidence_type='article',
        article_uri='pytest://own/page', relationship='originates',
        independence_key='owned:vendor_web')
    state = entity_events.recompute_corroboration(conn, result['event_id'])
    assert state['corroboration'] == 'vendor_claim'


def test_contradicting_evidence_keeps_the_event_and_flags_it(
        conn, brand, owned_article, press_article):
    """A disputed event that disappears looks exactly like one that never
    happened."""
    result = _round(conn, brand, [
        {'evidence_type': 'article', 'article_uri': owned_article,
         'relationship': 'originates', 'independence_key': 'owned:x'}])
    entity_events.add_evidence(
        conn, result['event_id'], evidence_type='article',
        article_uri=press_article, relationship='contradicts',
        independence_key='domain:techcrunch.com')
    state = entity_events.recompute_corroboration(conn, result['event_id'])
    assert state['status'] == 'pending_review'
    assert state['contradicting_sources'] == 1

    still_there = conn.execute(text("""
        SELECT status FROM bw_entity_events WHERE id = :e
    """), {'e': result['event_id']}).scalar()
    assert still_there == 'pending_review'


def test_an_undated_event_projects_with_a_null_date(conn, brand):
    """bw_market_events.event_date lost its NOT NULL for exactly this: an
    event whose date nobody stated must not be given one."""
    conn.execute(text("""
        INSERT INTO bw_markets (name, slug) VALUES ('Pytest M', 'pytest-m')
    """))
    market_id = conn.execute(text(
        "SELECT id FROM bw_markets WHERE slug = 'pytest-m'")).scalar()
    conn.execute(text("""
        INSERT INTO bw_market_brands (market_id, brand_id, baseline)
        VALUES (:m, :b, '{}'::jsonb)
    """), {'m': market_id, 'b': brand})

    result = entity_events.record(
        conn, event_type='headcount_change', title='Headcount moved',
        description='Between two readings.', brand_ids={brand: 'subject'},
        occurred_at=None, precision='unknown', evidence=[])

    row = conn.execute(text("""
        SELECT event_date, entity_event_id FROM bw_market_events
         WHERE entity_event_id = :e
    """), {'e': result['event_id']}).mappings().first()
    assert row is not None
    assert row['event_date'] is None


def test_a_dated_event_cannot_claim_unknown_precision(conn, brand):
    """The schema refuses the inconsistent combination outright."""
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        conn.execute(text("""
            INSERT INTO bw_entity_events
                (event_type, title, description, occurred_at, date_precision,
                 dedupe_hash)
            VALUES ('funding_round', 't', 'd', NOW(), 'unknown', 'pytest-bad')
        """))


# ---------------------------------------------------------------------------
# Narratives
# ---------------------------------------------------------------------------

def test_a_figure_that_is_not_in_the_facts_is_reported(conn, brand):
    facts = entity_narratives.build_facts(conn, brand)
    problems = entity_narratives.lint(
        'Pytest Events Co grew to 452 staff after raising 88 million.', facts)
    values = {p['value'] for p in problems if p['kind'] == 'unsupported_number'}
    assert values == {'452', '88'}


def test_figures_taken_from_the_facts_pass(conn, brand):
    facts = entity_narratives.build_facts(conn, brand)
    clean = (f"{facts['display_name']} has {facts['event_count']} recorded "
             f"events in the last {facts['window_days']} days. No external "
             f"mentions have been collected, which is a gap in coverage.")
    assert entity_narratives.lint(clean, facts) == []


def test_no_coverage_must_be_stated_as_a_gap(conn, brand):
    """Silence in our pipeline is not silence in the market, and prose that
    blurs the two is making a claim about the world from an absence in us."""
    facts = entity_narratives.build_facts(conn, brand)
    assert facts['external_mention_count'] == 0
    problems = entity_narratives.lint(
        'Nobody is talking about Pytest Events Co.', facts)
    assert any(p['kind'] == 'silence_read_as_absence' for p in problems)


def test_the_facts_pack_says_what_is_missing(conn, brand):
    """What we do not know is part of the brief, not an omission from it."""
    facts = entity_narratives.build_facts(conn, brand)
    assert 'employee_count' in facts['missing_fields']
    assert facts['coverage_caveats']


def test_saving_a_narrative_records_its_evidence_and_lint(conn, brand):
    facts = entity_narratives.build_facts(conn, brand)
    evidence = entity_narratives.evidence_from_facts(facts)
    saved = entity_narratives.save_narrative(
        conn, brand_id=brand, narrative='A cautious summary with no figures.',
        facts=facts, evidence=evidence)
    assert saved['clean'] is True

    stored = conn.execute(text("""
        SELECT narrative_type, status, facts, generator_version
          FROM bw_tracker_narratives WHERE id = :i
    """), {'i': saved['narrative_id']}).mappings().first()
    assert stored['narrative_type'] == 'brand_brief'
    assert stored['status'] == 'draft'
    assert stored['facts']['brand_id'] == brand


def test_a_regenerated_brief_supersedes_rather_than_overwrites(conn, brand):
    """A reader should be able to see that the assessment moved, and when."""
    facts = entity_narratives.build_facts(conn, brand)
    first = entity_narratives.save_narrative(
        conn, brand_id=brand, narrative='First take.', facts=facts)
    second = entity_narratives.save_narrative(
        conn, brand_id=brand, narrative='Second take.', facts=facts)

    assert second['supersedes_id'] == first['narrative_id']
    previous_status = conn.execute(text("""
        SELECT status FROM bw_tracker_narratives WHERE id = :i
    """), {'i': first['narrative_id']}).scalar()
    assert previous_status == 'superseded'


def test_lint_problems_are_stored_with_the_draft(conn, brand):
    """A draft that fails lint is kept with its failures attached, so the
    problem is reviewable rather than silently discarded."""
    facts = entity_narratives.build_facts(conn, brand)
    saved = entity_narratives.save_narrative(
        conn, brand_id=brand, narrative='They now employ 999 people.',
        facts=facts)
    assert saved['clean'] is False
    stored = conn.execute(text("""
        SELECT lint FROM bw_tracker_narratives WHERE id = :i
    """), {'i': saved['narrative_id']}).scalar()
    assert any(p['value'] == '999' for p in stored)
