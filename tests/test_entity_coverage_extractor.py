"""Earned coverage: what may raise belief in an event, and what may not.

The coverage extractor exists to move an event off the vendor's own word. That
makes its failure mode specific and expensive: a corroboration it invents is
manufactured consensus, produced by the system whose purpose is to detect it.
So most of what is pinned here is the extractor declining to match.

Three guards carry that weight. Sharing the company's name proves nothing,
because both texts carry it by construction. Sharing an event type proves
nothing, because a vendor can ship twice in a fortnight. And a press-release
wire is the company talking through a channel it paid for, so it must not read
as an outside source however many outlets carry it.

The pure tests need no database. The last one does, and rolls back.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.services import entity_events
from app.services.entity_event_extractors import coverage

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='coverage extraction is exercised against PostgreSQL')

WHEN = datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc)


def _event(ident, title, description=''):
    return {'id': ident, 'title': title, 'description': description,
            'occurred_at': WHEN, 'corroboration': 'vendor_claim'}


def _match(article, events, vendor='Torq'):
    return coverage._best_match(article, events,
                                coverage._name_tokens(vendor))


# ---------------------------------------------------------------------------
# What must not match
# ---------------------------------------------------------------------------

def test_the_vendor_name_alone_does_not_corroborate():
    """Both texts name the company. That is how they were selected."""
    events = [_event(1, 'Torq launches Auto Triage',
                     'Torq announced Auto Triage.')]
    assert _match('Torq announces a new product', events) is None


def test_market_boilerplate_does_not_corroborate():
    """Every headline in this market says security, platform and automation."""
    events = [_event(1, 'Torq launches Auto Triage',
                     'Torq announced Auto Triage.')]
    assert _match('Security platform announces new automation', events) is None


def test_two_launches_by_one_vendor_stay_apart():
    """A fortnight holds more than one launch, and the press about the second
    must not become evidence for the first."""
    events = [_event(1, 'Torq launches Auto Triage', 'Auto Triage triages.'),
              _event(2, 'Torq launches HyperSOC 2.0', 'HyperSOC 2.0 ships.')]
    assert _match('Torq debuts Auto Triage to cut alert load', events)['id'] == 1
    assert _match('Torq ships HyperSOC 2.0 upgrade', events)['id'] == 2


def test_a_different_round_is_not_the_same_round():
    """$33M and $60M are different events however alike the sentences read."""
    events = [_event(3, 'Simbian raises $33M Series A led by Accel',
                     'Simbian raised $33M.')]
    assert _match('Simbian lands $33M to expand', events, 'Simbian')['id'] == 3
    assert _match('Simbian raises $60M Series B', events, 'Simbian') is None


# ---------------------------------------------------------------------------
# Wires, and who is really speaking
# ---------------------------------------------------------------------------

def test_a_press_release_wire_is_not_a_newsroom():
    assert coverage._is_wire('globenewswire.com', None)
    assert coverage._is_wire(None, 'https://www.prnewswire.com/news/x')
    assert not coverage._is_wire('hackernoon.com', None)


def test_one_publisher_spelled_two_ways_is_one_voice():
    """Earned rows here arrive with an empty url, so the key comes off
    ``news_source``, and the corpus holds more than one spelling."""
    assert (coverage._source_key('HackerNoon.com', None, None)
            == coverage._source_key('hackernoon.com', None, None))
    assert coverage._source_key('hackernoon.com', None, None).startswith('domain:')


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
        VALUES ('pytest-coverage', 'Pytest Coverage Co', '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()


def test_a_trade_report_lifts_the_vendors_own_claim(conn, brand):
    """The point of the whole extractor, end to end at the evidence layer.

    A vendor announcing its own launch is a ``vendor_claim``. One unconnected
    publisher reporting the same launch makes it ``single_source`` — without
    displacing the vendor post, which stays the first place we saw it.
    """
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url, bias_source)
        VALUES ('pytest://cov/post', 'We launched Gamebooks', 'Ours.',
                'linkedin', 'https://linkedin.com/posts/9', 'vendor:linkedin')
    """))
    event = entity_events.record(
        conn, event_type='product_launch', title='Gamebooks launch',
        description='Gamebooks is available.', brand_ids={brand: 'subject'},
        attributes={'announced_by': 'vendor'}, occurred_at=WHEN,
        evidence=[{'evidence_type': 'article',
                   'article_uri': 'pytest://cov/post',
                   'relationship': 'originates',
                   'independence_key': 'owned:vendor:linkedin'}])
    assert event['corroboration'] == 'vendor_claim'

    entity_events.add_evidence(
        conn, event['event_id'], evidence_type='article',
        article_uri='pytest://cov/post', relationship='supports',
        independence_key=coverage._source_key('hackernoon.com', None, None))
    after = entity_events.recompute_corroboration(conn, event['event_id'])
    assert after['corroboration'] == 'single_source'
    assert after['owned_sources'] == 1, 'the vendor post must still be attached'


def test_a_wire_release_lifts_nothing(conn, brand):
    """A company paying to distribute its announcement has not been
    corroborated by anyone."""
    conn.execute(text("""
        INSERT INTO articles (uri, title, news_source, bias_source)
        VALUES ('pytest://cov/wpost', 'We launched', 'linkedin', 'vendor:linkedin'),
               ('pytest://cov/wire', 'Co launches', 'globenewswire.com', NULL)
    """))
    event = entity_events.record(
        conn, event_type='product_launch', title='Wire launch',
        description='Announced.', brand_ids={brand: 'subject'},
        attributes={'announced_by': 'vendor'}, occurred_at=WHEN,
        evidence=[{'evidence_type': 'article',
                   'article_uri': 'pytest://cov/wpost',
                   'relationship': 'originates',
                   'independence_key': 'owned:vendor:linkedin'}])
    entity_events.add_evidence(
        conn, event['event_id'], evidence_type='article',
        article_uri='pytest://cov/wire', relationship='supports',
        independence_key='owned:wire:pytest coverage co')
    after = entity_events.recompute_corroboration(conn, event['event_id'])
    assert after['corroboration'] == 'vendor_claim'
    assert after['independent_sources'] == 0
