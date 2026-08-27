"""Linking entities to content, and the mistakes that would corrupt a feed.

The failures pinned here are the ones that make a vendor page lie rather than
merely look empty: a company's own announcement counted as somebody praising
it, two vendors in one post sharing a single score, a name matched inside
another company's URL, and an account claimed by whoever guessed first.

The pure tests need nothing. The rest run inside a transaction that is always
rolled back, so they exercise the real constraints without leaving rows.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.services import entity_content
from app.services.social_sources import (
    classify_source, is_social_row, is_social_source,
)

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='entity ingestion is exercised against PostgreSQL')


# ---------------------------------------------------------------------------
# Channel classification — pure
# ---------------------------------------------------------------------------

def test_a_vendors_own_post_is_owned_not_earned():
    """The distinction the whole reputation figure depends on."""
    assert classify_source('linkedin', 'vendor:linkedin') == ('linkedin',
                                                              'owned_social')


def test_platforms_are_named_rather_than_guessed():
    assert classify_source('xpoz:twitter') == ('twitter', 'public_social')
    assert classify_source('xpoz:tiktok') == ('tiktok', 'public_social')
    assert classify_source('bluesky') == ('bluesky', 'public_social')


def test_reddit_is_community_not_broadcast():
    """A subreddit is a room, not a megaphone, and its sentiment reads
    differently from a public post."""
    assert classify_source('xpoz:reddit') == ('reddit', 'community')
    assert classify_source('reddit.com') == ('reddit', 'community')


def test_news_is_earned_and_has_no_platform():
    assert classify_source('techmeme.com') == (None, 'earned_news')
    assert classify_source(None) == (None, 'earned_news')


def test_a_domain_containing_a_platform_name_is_not_social():
    """clsbluesky.law.columbia.edu is a law-school blog. The old substring
    helper calls it social; classification does not, and both answers are kept
    so the seventeen existing callers of the old helper do not change."""
    assert is_social_row('clsbluesky.law.columbia.edu') is False
    assert is_social_source('clsbluesky.law.columbia.edu') is True


# ---------------------------------------------------------------------------
# Term matching — pure
# ---------------------------------------------------------------------------

def test_a_name_inside_someone_elses_url_is_not_a_mention():
    """A post about 7AI linking to whois-secure.com matched the vendor
    Secure.com, because a hyphen reads as a word boundary."""
    terms = [{'id': 1, 'brand_id': 10, 'term': 'Secure.com',
              'normalized_term': 'secure.com', 'term_kind': 'name'}]
    blob = ('Exciting news! 7AI has launched AI-driven tools '
            'https://whois-secure.com/blog/7ai-ai-threat-detection')
    assert entity_content.candidates_from_terms(blob, terms) == []


def test_a_name_in_the_prose_is_a_mention():
    terms = [{'id': 1, 'brand_id': 10, 'term': 'Radiant Security',
              'normalized_term': 'radiant security', 'term_kind': 'name'}]
    blob = 'Cribl has acquired AI technology assets from Radiant Security.'
    found = entity_content.candidates_from_terms(blob, terms)
    assert [c['brand_id'] for c in found] == [10]
    assert 'Radiant Security' in found[0]['excerpt']


def test_matching_stops_at_word_boundaries():
    terms = [{'id': 1, 'brand_id': 10, 'term': '7ai',
              'normalized_term': '7ai', 'term_kind': 'name'}]
    assert entity_content.candidates_from_terms('the 7aints played', terms) == []
    assert entity_content.candidates_from_terms('7ai launched', terms)


def test_one_post_can_name_two_vendors():
    terms = [
        {'id': 1, 'brand_id': 10, 'term': 'Crogl',
         'normalized_term': 'crogl', 'term_kind': 'name'},
        {'id': 2, 'brand_id': 11, 'term': 'Prophet Security',
         'normalized_term': 'prophet security', 'term_kind': 'name'},
    ]
    blob = ('AI SOC roundup: Crogl offers a free air-gap-capable agent, '
            'Prophet Security an AI-driven detection engineer.')
    assert sorted(c['brand_id'] for c in
                  entity_content.candidates_from_terms(blob, terms)) == [10, 11]


def test_ordinary_words_need_qualification_and_coined_names_do_not():
    """The test is the word, not the vendor. Nobody else writes "Qevlar";
    everybody writes "Radiant"."""
    assert entity_content.is_safe_standalone('qevlar') is True
    assert entity_content.is_safe_standalone('intezer') is True
    assert entity_content.is_safe_standalone('radiant') is False
    assert entity_content.is_safe_standalone('cantina') is False
    assert entity_content.is_safe_standalone('7ai') is False
    assert entity_content.is_safe_standalone('radiant security') is True


def test_mention_identity_ignores_time():
    """The same post found again by the same term is the same mention,
    whenever the collector happened to see it."""
    first = entity_content.dedupe_hash_for(
        mention_type='explicit_name', matched_term='Crogl',
        channel='public_social')
    second = entity_content.dedupe_hash_for(
        mention_type='explicit_name', matched_term='crogl ',
        channel='public_social')
    assert first == second


# ---------------------------------------------------------------------------
# Against the real schema
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    from app.database import get_database_instance

    db = get_database_instance()
    connection = db._temp_get_connection()
    if connection.execute(
            text("SELECT to_regclass('bw_entity_content_links')")).scalar() is None:
        connection.close()
        pytest.skip('ei_002 has not been applied to this database')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture()
def brands(conn):
    ids = []
    for slug in ('pytest-ingest-a', 'pytest-ingest-b'):
        ids.append(conn.execute(text("""
            INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
            VALUES (:n, :d, '[]'::jsonb, FALSE) RETURNING id
        """), {'n': slug, 'd': slug.title()}).scalar())
    return ids


@pytest.fixture()
def article(conn):
    uri = 'pytest://entity-ingestion/post-1'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url)
        VALUES (:u, 'Crogl and Prophet Security both shipped triage agents',
                'A roundup post.', 'xpoz:twitter', 'https://example.invalid/1')
    """), {'u': uri})
    return uri


def test_one_article_links_to_two_entities_without_being_copied(
        conn, brands, article):
    """One row in articles, two relationships. The body is never duplicated."""
    for brand_id in brands:
        entity_content.link_content(
            conn, brand_id=brand_id, article_uri=article,
            relationship='mentions', channel='public_social',
            platform='twitter', attribution_method='query_term')

    links = conn.execute(text("""
        SELECT count(*) FROM bw_entity_content_links WHERE article_uri = :u
    """), {'u': article}).scalar()
    articles = conn.execute(text("""
        SELECT count(*) FROM articles WHERE uri = :u
    """), {'u': article}).scalar()
    assert links == 2
    assert articles == 1


def test_each_vendor_gets_its_own_verdict_on_the_same_post(
        conn, brands, article):
    """The defect this table exists to fix: one post, one score, inherited by
    whichever company was evaluated second."""
    first, second = brands
    a = entity_content.record_mention(
        conn, brand_id=first, article_uri=article, mention_type='explicit_name',
        channel='public_social', platform='twitter', matched_term='Crogl')
    b = entity_content.record_mention(
        conn, brand_id=second, article_uri=article, mention_type='explicit_name',
        channel='public_social', platform='twitter',
        matched_term='Prophet Security')

    entity_content.score_mention(conn, a, relevance=0.9, sentiment='positive',
                                 stance='supportive', method='llm')
    entity_content.score_mention(conn, b, relevance=0.4, sentiment='negative',
                                 stance='critical', method='llm')

    rows = dict(conn.execute(text("""
        SELECT brand_id, sentiment FROM bw_entity_mentions WHERE article_uri = :u
    """), {'u': article}).fetchall())
    assert rows[first] == 'positive'
    assert rows[second] == 'negative'


def test_relinking_the_same_relationship_does_not_multiply(conn, brands, article):
    """A brand with three category rows on one article is one relationship."""
    brand_id = brands[0]
    for _ in range(3):
        entity_content.link_content(
            conn, brand_id=brand_id, article_uri=article,
            relationship='mentions', channel='public_social',
            attribution_method='classifier')
    count = conn.execute(text("""
        SELECT count(*) FROM bw_entity_content_links
         WHERE brand_id = :b AND article_uri = :u
    """), {'b': brand_id, 'u': article}).scalar()
    assert count == 1


def test_an_owned_post_is_a_claim_and_carries_no_sentiment(conn, brands, article):
    """A company praising itself is not evidence anyone else did, so it never
    enters external sentiment however glowing it is."""
    brand_id = brands[0]
    entity_content.record_mention(
        conn, brand_id=brand_id, article_uri=article,
        mention_type='owned_attribution', channel='owned_social',
        platform='linkedin', relevance=1.0, sentiment=None,
        stance='owned_claim', status='accepted',
        evaluation_method='attribution')
    row = conn.execute(text("""
        SELECT stance, sentiment, relevance FROM bw_entity_mentions
         WHERE brand_id = :b AND article_uri = :u
    """), {'b': brand_id, 'u': article}).mappings().first()
    assert row['stance'] == 'owned_claim'
    assert row['sentiment'] is None
    assert float(row['relevance']) == 1.0


def test_a_found_mention_is_not_a_judged_one(conn, brands, article):
    """Pending means nobody has decided yet. Counting it as neutral would put
    an opinion in the figures that nothing ever formed."""
    mention_id = entity_content.record_mention(
        conn, brand_id=brands[0], article_uri=article,
        mention_type='explicit_name', channel='public_social',
        matched_term='Crogl')
    row = conn.execute(text("""
        SELECT status, sentiment, evaluated_at FROM bw_entity_mentions
         WHERE id = :i
    """), {'i': mention_id}).mappings().first()
    assert row['status'] == 'pending'
    assert row['sentiment'] is None
    assert row['evaluated_at'] is None


# ---------------------------------------------------------------------------
# Social identity
# ---------------------------------------------------------------------------

def test_a_renamed_account_stays_one_identity(conn):
    """Same platform id, new handle: one account, with the old handle kept.
    Otherwise the mapped account goes quiet and an unmapped one appears."""
    from app.services import entity_identity

    first = entity_identity.upsert_account(
        conn, platform='bluesky', handle='oldname.bsky.social',
        platform_user_id='did:plc:example123')
    second = entity_identity.upsert_account(
        conn, platform='bluesky', handle='newname.bsky.social',
        platform_user_id='did:plc:example123')

    assert first['account_id'] == second['account_id']
    assert second['renamed'] is True

    row = conn.execute(text("""
        SELECT handle, metadata FROM social_accounts WHERE id = :i
    """), {'i': first['account_id']}).mappings().first()
    assert row['handle'] == 'newname.bsky.social'
    history = [h['handle'] for h in row['metadata']['handle_history']]
    assert 'oldname.bsky.social' in history


def test_a_name_lookalike_is_proposed_and_never_verified(conn, brands):
    """Handles collide and companies get impersonated, so resemblance can
    nominate but must not confirm."""
    from app.services import entity_identity

    account = entity_identity.upsert_account(
        conn, platform='twitter', handle='crogl')
    outcome = entity_identity.propose_identity(
        conn, brand_id=brands[0], social_account_id=account['account_id'],
        relationship='owned_company', verification_method='content_inference',
        provenance={'evidence': 'handle resembles the display name'})
    assert outcome['status'] == 'proposed'


def test_direct_provider_evidence_verifies(conn, brands):
    """The collector asked for this company's page by its verified URL, so the
    mapping is not a guess."""
    from app.services import entity_identity

    account = entity_identity.upsert_account(
        conn, platform='linkedin', handle='company/example',
        platform_user_id='company/example')
    outcome = entity_identity.propose_identity(
        conn, brand_id=brands[0], social_account_id=account['account_id'],
        relationship='owned_company', verification_method='provider')
    assert outcome['status'] == 'verified'


def test_two_companies_claiming_one_account_is_a_review_task(conn, brands):
    """Whichever way it is settled, somebody's brand monitoring has been
    reading the wrong feed, so nothing is settled automatically."""
    from app.services import entity_identity

    account = entity_identity.upsert_account(
        conn, platform='twitter', handle='contested', platform_user_id='42')
    first = entity_identity.propose_identity(
        conn, brand_id=brands[0], social_account_id=account['account_id'],
        relationship='owned_company', verification_method='provider')
    second = entity_identity.propose_identity(
        conn, brand_id=brands[1], social_account_id=account['account_id'],
        relationship='owned_company', verification_method='provider')

    assert first['status'] == 'verified'
    assert second['status'] == 'disputed'
    assert second['identity_id'] is None

    tasks = conn.execute(text("""
        SELECT severity FROM bw_review_tasks
         WHERE kind = 'identity_conflict' AND brand_id = :b AND status = 'open'
    """), {'b': brands[1]}).fetchall()
    assert [t[0] for t in tasks] == ['high']


def test_an_executive_account_needs_a_person_to_confirm_it(conn, brands):
    """A claim about an individual is not something a name match can support."""
    from app.services import entity_identity

    account = entity_identity.upsert_account(
        conn, platform='twitter', handle='some-ceo')
    outcome = entity_identity.propose_identity(
        conn, brand_id=brands[0], social_account_id=account['account_id'],
        relationship='executive', verification_method='content_inference')
    assert outcome['identity_id'] is None
    assert 'manual confirmation' in outcome['reason']


def test_a_rejected_mapping_is_not_proposed_again(conn, brands):
    """Rejections are kept so the same wrong guess is not re-made on the next
    pass, which is how a review queue becomes noise people stop reading."""
    from app.services import entity_identity

    account = entity_identity.upsert_account(
        conn, platform='twitter', handle='not-us')
    first = entity_identity.propose_identity(
        conn, brand_id=brands[0], social_account_id=account['account_id'],
        relationship='unofficial', verification_method='content_inference')
    entity_identity.reject_identity(conn, first['identity_id'],
                                    actor='pytest', reason='different company')

    again = entity_identity.propose_identity(
        conn, brand_id=brands[0], social_account_id=account['account_id'],
        relationship='unofficial', verification_method='content_inference')
    assert again['identity_id'] is None
    assert 'previously rejected' in again['reason']

    # A person may still overrule it.
    manual = entity_identity.propose_identity(
        conn, brand_id=brands[0], social_account_id=account['account_id'],
        relationship='unofficial', verification_method='manual',
        actor='pytest')
    assert manual['status'] == 'verified'


# ---------------------------------------------------------------------------
# A reshare is not the company speaking
# ---------------------------------------------------------------------------

def test_the_provider_sample_maps_and_keeps_what_decides_ownership():
    """Checked against the Bright Data dashboard sample for the posts dataset.

    ``account_type`` and ``repost`` were both being discarded, and both decide
    whether a post is the vendor's own claim."""
    from app.services.brightdata_linkedin import map_company_post

    sample = {
        'id': '7447791645200211968',
        'url': 'https://www.linkedin.com/posts/x-activity-7447791645200211968',
        'user_id': 'ausbiz-capital',
        'use_url': 'https://au.linkedin.com/company/ausbiz-capital?trk=public_post',
        'headline': 'Direct Access.',
        'post_text': 'Direct Access. Real Market Insights.',
        'date_posted': '2026-04-08T23:45:01.477Z',
        'num_likes': 3, 'num_comments': 0, 'user_followers': 139,
        'account_type': 'Organization', 'post_type': 'post',
        'user_name': 'ausbiz capital',
        'repost': {'repost_id': None, 'repost_url': None},
    }
    mapped = map_company_post(sample)
    assert mapped is not None, 'the dashboard sample would have been dropped'
    assert mapped['external_id'] == '7447791645200211968'
    assert mapped['account_type'] == 'Organization'
    assert mapped['is_repost'] is False


def test_a_reshare_is_detected_from_the_repost_object():
    """The provider returns a repost object on every record and fills it only
    for a reshare, so its presence proves nothing — its contents do."""
    from app.services.brightdata_linkedin import map_company_post

    base = {'id': '1', 'url': 'https://x/1', 'post_text': 'body',
            'user_name': 'Vendor', 'use_url': 'https://linkedin.com/company/v'}
    assert map_company_post(
        {**base, 'repost': {'repost_id': None}})['is_repost'] is False
    assert map_company_post(
        {**base, 'repost': {'repost_id': '99',
                            'repost_user_name': 'Someone'}})['is_repost'] is True


def test_a_reshared_post_is_linked_but_is_not_an_owned_claim(conn, brands):
    """A vendor amplifying an analyst is not the vendor claiming anything.
    Marking it owned_claim at relevance 1.0 puts words in their mouth."""
    import json

    from app.services import entity_ingest

    uri = 'pytest://owned/reshare'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url,
                              bias_source, social_meta, publication_date)
        VALUES (:u, 'Reshared analyst take', 'body', 'linkedin',
                'https://x/1', 'vendor:linkedin', CAST(:meta AS JSONB),
                '2026-08-20T00:00:00')
    """), {'u': uri, 'meta': json.dumps({'platform': 'linkedin',
                                         'account_type': 'Organization',
                                         'is_repost': True})})
    conn.execute(text("""
        INSERT INTO bw_article_categories (article_uri, brand_id, category)
        VALUES (:u, :b, 'Product & Innovation')
    """), {'u': uri, 'b': brands[0]})

    entity_ingest.link_content(conn, uri)

    row = conn.execute(text("""
        SELECT stance, relevance FROM bw_entity_mentions
         WHERE article_uri = :u AND brand_id = :b
    """), {'u': uri, 'b': brands[0]}).mappings().first()
    assert row is not None, 'the post should still be linked and visible'
    assert row['stance'] == 'not_applicable'
    assert row['stance'] != 'owned_claim'


def test_the_companys_own_post_is_still_an_owned_claim(conn, brands):
    import json

    from app.services import entity_ingest

    uri = 'pytest://owned/genuine'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url,
                              bias_source, social_meta, publication_date)
        VALUES (:u, 'We shipped a thing', 'body', 'linkedin', 'https://x/2',
                'vendor:linkedin', CAST(:meta AS JSONB), '2026-08-20T00:00:00')
    """), {'u': uri, 'meta': json.dumps({'platform': 'linkedin',
                                         'account_type': 'Organization',
                                         'is_repost': False})})
    conn.execute(text("""
        INSERT INTO bw_article_categories (article_uri, brand_id, category)
        VALUES (:u, :b, 'Product & Innovation')
    """), {'u': uri, 'b': brands[0]})

    entity_ingest.link_content(conn, uri)

    row = conn.execute(text("""
        SELECT stance FROM bw_entity_mentions
         WHERE article_uri = :u AND brand_id = :b
    """), {'u': uri, 'b': brands[0]}).mappings().first()
    assert row['stance'] == 'owned_claim'


def test_posts_collected_before_these_fields_existed_still_read_as_owned(
        conn, brands):
    """The historical corpus has no account_type or is_repost. Treating those
    as not-the-company would silently reclassify 1,209 existing posts."""
    from app.services import entity_ingest

    uri = 'pytest://owned/legacy'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url,
                              bias_source, publication_date)
        VALUES (:u, 'Older post', 'body', 'linkedin', 'https://x/3',
                'vendor:linkedin', '2026-07-01T00:00:00')
    """), {'u': uri})
    conn.execute(text("""
        INSERT INTO bw_article_categories (article_uri, brand_id, category)
        VALUES (:u, :b, 'Product & Innovation')
    """), {'u': uri, 'b': brands[0]})

    entity_ingest.link_content(conn, uri)

    row = conn.execute(text("""
        SELECT stance FROM bw_entity_mentions
         WHERE article_uri = :u AND brand_id = :b
    """), {'u': uri, 'b': brands[0]}).mappings().first()
    assert row['stance'] == 'owned_claim'


def test_a_page_on_the_vendors_own_domain_is_owned_web_not_earned_news(
        conn, brands):
    """The channel is decided per entity. A vendor's blog carries no
    bias_source, so classify_source calls it earned_news; for the vendor whose
    domain it is, that is the company writing about itself. 148 such links
    across 14 vendors read as outside coverage before this rule."""
    from app.services import entity_ingest

    brand_id = brands[0]
    domain = 'pytest-owned-domain.invalid'
    conn.execute(text("""
        INSERT INTO bw_vendor_identifiers
            (brand_id, kind, normalized_value, display_value, valid_from,
             provenance)
        VALUES (:b, 'domain', :d, :d, NOW(), CAST('{}' AS JSONB))
    """), {'b': brand_id, 'd': domain})
    uri = f'https://www.{domain}/blog/we-are-great'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url,
                              publication_date)
        VALUES (:u, 'We are great', 'body', 'Vendor Blog', :u,
                '2026-08-20T00:00:00')
    """), {'u': uri})

    entity_ingest.link_content(conn, uri, candidates=[{
        'brand_id': brand_id, 'attribution_method': 'keyword',
        'mention_type': 'explicit_name'}])

    link = conn.execute(text("""
        SELECT channel, relationship FROM bw_entity_content_links
         WHERE article_uri = :u AND brand_id = :b
    """), {'u': uri, 'b': brand_id}).mappings().first()
    assert link['channel'] == 'owned_web'
    assert link['relationship'] == 'owned'
    mention = conn.execute(text("""
        SELECT channel, stance FROM bw_entity_mentions
         WHERE article_uri = :u AND brand_id = :b
    """), {'u': uri, 'b': brand_id}).mappings().first()
    assert mention['channel'] == 'owned_web'
    assert mention['stance'] == 'owned_claim'


def test_the_same_page_is_earned_coverage_for_another_vendor_it_names(
        conn, brands):
    """Dropzone's blog writing about Crogl is Dropzone's own voice and genuine
    third-party coverage for Crogl. One article, two channels."""
    from app.services import entity_ingest

    if len(brands) < 2:
        pytest.skip('needs two vendors')
    owner, other = brands[0], brands[1]
    domain = 'pytest-owned-domain-two.invalid'
    conn.execute(text("""
        INSERT INTO bw_vendor_identifiers
            (brand_id, kind, normalized_value, display_value, valid_from,
             provenance)
        VALUES (:b, 'domain', :d, :d, NOW(), CAST('{}' AS JSONB))
    """), {'b': owner, 'd': domain})
    uri = f'https://{domain}/blog/on-a-rival'
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, url,
                              publication_date)
        VALUES (:u, 'On a rival', 'body', 'Vendor Blog', :u,
                '2026-08-20T00:00:00')
    """), {'u': uri})

    entity_ingest.link_content(conn, uri, candidates=[
        {'brand_id': owner, 'attribution_method': 'keyword',
         'mention_type': 'explicit_name'},
        {'brand_id': other, 'attribution_method': 'keyword',
         'mention_type': 'explicit_name'},
    ])

    channels = dict(conn.execute(text("""
        SELECT brand_id, channel FROM bw_entity_content_links
         WHERE article_uri = :u
    """), {'u': uri}).fetchall())
    assert channels[owner] == 'owned_web'
    assert channels[other] == 'earned_news'
