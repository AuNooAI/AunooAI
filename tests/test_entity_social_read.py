"""The social feed read per company rather than per topic.

What the old shape could not do is the subject here. A vendor's own LinkedIn
post and somebody's critical Reddit thread were both just rows in the feed with
a sentiment on them, so a rollup counted the company's own marketing as
evidence of how it was received. And a post naming two companies had one score
between them.

These tests pin the separations that fix that, and the compatibility adapter
that lets the existing tab keep calling with a topic string.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.services import entity_social_read as esr

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='the social read is exercised against PostgreSQL')


# ---------------------------------------------------------------------------
# Compatibility adapter — pure enough to reason about
# ---------------------------------------------------------------------------

def test_the_platform_filter_covers_every_network_we_collect():
    for platform in ('reddit', 'bluesky', 'twitter', 'instagram', 'tiktok',
                     'linkedin'):
        assert platform in esr.SOURCE_PLATFORMS


def test_x_is_an_alias_for_twitter():
    assert esr.SOURCE_PLATFORMS['x'] == esr.SOURCE_PLATFORMS['twitter']


def test_owned_channels_are_named_once():
    assert 'owned_social' in esr.OWNED_CHANNELS
    assert 'public_social' not in esr.OWNED_CHANNELS


# ---------------------------------------------------------------------------
# Against real rows
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    from app.database import get_database_instance

    db = get_database_instance()
    connection = db._temp_get_connection()
    if connection.execute(
            text("SELECT to_regclass('bw_entity_mentions')")).scalar() is None:
        connection.close()
        pytest.skip('ei_002 has not been applied to this database')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture()
def brand(conn):
    return conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-social', 'Pytest Social Co', '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()


def _mention(conn, brand, *, uri, channel, platform, sentiment=None,
             stance=None, relevance=None, status='pending', title='A post'):
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url,
                              publication_date)
        VALUES (:u, :t, 'body', :ns, 'https://x.test', '2026-08-20T00:00:00')
        ON CONFLICT (uri) DO NOTHING
    """), {'u': uri, 't': title, 'ns': platform})
    conn.execute(text("""
        INSERT INTO bw_entity_mentions
            (brand_id, article_uri, mention_type, channel, platform,
             relevance, sentiment, stance, status, dedupe_hash, evaluated_at)
        VALUES (:b, :u, 'explicit_name', :ch, :plat, :rel, :sent, :stance,
                :status, :hash,
                CASE WHEN :rel IS NULL THEN NULL ELSE NOW() END)
    """), {'b': brand, 'u': uri, 'ch': channel, 'plat': platform,
           'rel': relevance, 'sent': sentiment, 'stance': stance,
           'status': status, 'hash': uri})


def test_topics_resolve_to_a_company(conn, brand):
    """The existing tab passes 'Brand Monitoring <name>' and must keep working."""
    assert esr.brands_for_topics(conn, 'Brand Monitoring Pytest Social Co') == [brand]


def test_an_unknown_topic_resolves_to_nothing_not_everything(conn):
    assert esr.brands_for_topics(conn, 'Brand Monitoring Nobody Ltd') == []
    assert esr.brands_for_topics(conn, None) == []


def test_a_companys_own_posts_are_hidden_unless_asked_for(conn, brand):
    _mention(conn, brand, uri='pytest://s/own', channel='owned_social',
             platform='linkedin', stance='owned_claim', relevance=1.0,
             status='accepted')
    _mention(conn, brand, uri='pytest://s/public', channel='public_social',
             platform='twitter')

    hidden = esr.social_feed(conn, brand_ids=[brand], days_back=3650)
    assert hidden['total'] == 1
    assert hidden['owned_total'] == 0

    shown = esr.social_feed(conn, brand_ids=[brand], days_back=3650,
                            include_owned=True)
    assert shown['total'] == 2
    assert shown['owned_total'] == 1


def test_owned_posts_never_reach_the_sentiment_denominator(conn, brand):
    """A company praising itself is not evidence anybody else did."""
    _mention(conn, brand, uri='pytest://s/own2', channel='owned_social',
             platform='linkedin', sentiment='Positive', stance='owned_claim',
             relevance=1.0, status='accepted')
    feed = esr.social_feed(conn, brand_ids=[brand], days_back=3650,
                           include_owned=True)
    assert feed['owned_total'] == 1
    assert feed['sentiment_denominator'] == 0
    assert feed['by_sentiment'] == {}


def test_unevaluated_mentions_are_counted_apart_from_neutral(conn, brand):
    """Folding them in would report a settled balance of opinion assembled
    from posts nobody read."""
    _mention(conn, brand, uri='pytest://s/judged', channel='public_social',
             platform='bluesky', sentiment='Negative', relevance=0.8,
             status='accepted')
    _mention(conn, brand, uri='pytest://s/pending', channel='public_social',
             platform='bluesky')

    feed = esr.social_feed(conn, brand_ids=[brand], days_back=3650)
    assert feed['total'] == 2
    assert feed['unevaluated_total'] == 1
    assert feed['sentiment_denominator'] == 1
    assert feed['by_sentiment'] == {'Negative': 1}
    assert any('not been evaluated' in note for note in feed['coverage_notes'])


def test_no_coverage_is_reported_as_a_gap(conn, brand):
    feed = esr.social_feed(conn, brand_ids=[brand], days_back=3650)
    assert feed['total'] == 0
    assert any('gap in collection' in note for note in feed['coverage_notes'])


def test_community_and_employee_content_are_distinguishable(conn, brand):
    """Reddit is a room, Glassdoor is staff, and neither reads like a public
    broadcast post."""
    _mention(conn, brand, uri='pytest://s/reddit', channel='community',
             platform='reddit')
    _mention(conn, brand, uri='pytest://s/glassdoor', channel='employee',
             platform='glassdoor')
    _mention(conn, brand, uri='pytest://s/x', channel='public_social',
             platform='twitter')

    feed = esr.social_feed(conn, brand_ids=[brand], days_back=3650)
    assert feed['by_channel'] == {'community': 1, 'employee': 1,
                                  'public_social': 1}


def test_the_platform_filter_narrows_to_one_network(conn, brand):
    _mention(conn, brand, uri='pytest://s/r', channel='community',
             platform='reddit')
    _mention(conn, brand, uri='pytest://s/b', channel='public_social',
             platform='bluesky')

    only_reddit = esr.social_feed(conn, brand_ids=[brand], days_back=3650,
                                  source='reddit')
    assert only_reddit['total'] == 1
    assert only_reddit['by_platform'] == {'reddit': 1}


def test_a_threshold_excludes_what_was_never_scored(conn, brand):
    _mention(conn, brand, uri='pytest://s/scored', channel='public_social',
             platform='twitter', relevance=0.9, sentiment='Positive',
             status='accepted')
    _mention(conn, brand, uri='pytest://s/unscored', channel='public_social',
             platform='twitter')

    feed = esr.social_feed(conn, brand_ids=[brand], days_back=3650,
                           min_relevance=0.5)
    assert feed['total'] == 1
    assert feed['posts'][0]['uri'] == 'pytest://s/scored'


def test_one_post_gives_two_companies_their_own_verdicts(conn, brand):
    """The defect the whole mention table exists to fix, at the read end."""
    other = conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-social-2', 'Pytest Social Two', '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()

    _mention(conn, brand, uri='pytest://s/shared', channel='public_social',
             platform='twitter', sentiment='Positive', relevance=0.9,
             status='accepted', title='Two vendors compared')
    _mention(conn, other, uri='pytest://s/shared', channel='public_social',
             platform='twitter', sentiment='Negative', relevance=0.4,
             status='accepted', title='Two vendors compared')

    first = esr.social_feed(conn, brand_ids=[brand], days_back=3650)
    second = esr.social_feed(conn, brand_ids=[other], days_back=3650)

    assert first['by_sentiment'] == {'Positive': 1}
    assert second['by_sentiment'] == {'Negative': 1}
    # One article, two verdicts, and the body was never copied.
    assert first['posts'][0]['uri'] == second['posts'][0]['uri']
