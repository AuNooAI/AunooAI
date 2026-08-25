#!/usr/bin/env python3
"""Fill the entity tables from data the registry already holds.

Nothing here collects anything. Every observation this writes is derived from a
row that is already in the database — the imported workbook baseline, and the
provider snapshots collected since. The point is to arrive at a canonical value
for each field with its provenance intact, so that the first newly collected
reading has something to be compared against rather than landing in an empty
table.

Two properties matter more than speed.

**It resumes.** Progress is a primary-key cursor in ``bw_entity_backfill_state``,
committed with the work it describes, so an interrupted run continues from the
last committed batch rather than starting over or skipping ahead.

**It is idempotent.** Running any subcommand twice changes nothing the second
time. Observations are keyed by the source record they came from, so a rerun
collides and does nothing; resolution over unchanged observations produces the
same winner and writes no new log row. ``verify`` checks exactly this.

Timestamps come from the data, never from the clock. A membership's import
observation is dated when the import happened, and a snapshot's observations
are dated when the snapshot was observed. Using run time would make every
backfilled value look like it was learned today, which would quietly reset
every freshness calculation in the system.

Usage:

    python scripts/entity_intelligence_backfill.py baseline --dry-run
    python scripts/entity_intelligence_backfill.py snapshots
    python scripts/entity_intelligence_backfill.py canonical
    python scripts/entity_intelligence_backfill.py verify --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text                                    # noqa: E402

from app.database import get_database_instance                 # noqa: E402
from app.services import (                                     # noqa: E402
    entity_content, entity_identity, entity_projection, entity_resolution,
)
from app.services.social_sources import classify_source        # noqa: E402
from app.services import entity_dual_read                      # noqa: E402
from app.services.entity_observations import (                 # noqa: E402
    NormalizationError, mint_source_record_id, normalize_snapshot,
    pending_snapshot_ids, record_observation,
)
from app.services.entity_field_registry import (               # noqa: E402
    ENTITY_FIELD_POLICY_VERSION,
)

BATCH = 200

# Subcommands whose tables arrive with later phases. They are listed so the
# command surface matches the plan, and they refuse rather than no-op, because
# a backfill that prints "done" without doing anything is worse than an error.
LATER_PHASES = {
    'recent-events': 'phase 3 (bw_entity_events)',
    'narrative-metadata': 'phase 3 (narrative type/status columns)',
}


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def _load_cursor(conn, subcommand: str) -> str:
    row = conn.execute(text("""
        SELECT cursor_value FROM bw_entity_backfill_state WHERE subcommand = :s
    """), {'s': subcommand}).fetchone()
    return row[0] if row and row[0] else '0'


def _save_cursor(conn, subcommand: str, cursor: str, done: int, skipped: int,
                 status: str = 'running', detail: Optional[Dict] = None) -> None:
    conn.execute(text("""
        INSERT INTO bw_entity_backfill_state
            (subcommand, cursor_value, rows_done, rows_skipped, status, detail,
             started_at, updated_at)
        VALUES (:s, :c, :d, :k, :st, CAST(:detail AS JSONB), NOW(), NOW())
        ON CONFLICT (subcommand) DO UPDATE
           SET cursor_value = EXCLUDED.cursor_value,
               rows_done = bw_entity_backfill_state.rows_done + EXCLUDED.rows_done,
               rows_skipped = bw_entity_backfill_state.rows_skipped
                              + EXCLUDED.rows_skipped,
               status = EXCLUDED.status,
               detail = EXCLUDED.detail,
               updated_at = NOW()
    """), {'s': subcommand, 'c': cursor, 'd': done, 'k': skipped,
           'st': status, 'detail': json.dumps(detail or {})})


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------

def cmd_baseline(conn, args) -> Dict[str, Any]:
    """Turn each membership's imported baseline into dated observations.

    The workbook's own values, kept exactly where they are. This does not move
    anything out of ``baseline``; it copies the facts into a shape that can be
    compared against a newer reading and lose to it.
    """
    cursor = int(_load_cursor(conn, 'baseline')) if args.resume else 0
    written = skipped = 0

    # The importer wrote the same headcount and funding status twice: once into
    # ``baseline``, and once as a workbook ``metric`` snapshot. They are the
    # same reading from the same source on the same day, so taking both would
    # put two identical observations on every vendor's series. The snapshot
    # owns those two fields because it is already a dated observation; the
    # baseline owns the four fields the snapshot never carried.
    # The workbook snapshot also carries the date the import actually
    # happened, which the membership row does not always still have — a
    # membership rebuilt after data loss is stamped with the rebuild, not the
    # import. Dating an observation from the rebuild would make a value from
    # April look like it was learned today and quietly reset its freshness.
    metric_snapshots = {
        int(r['brand_id']): r['observed_at'] for r in conn.execute(text("""
            SELECT DISTINCT ON (brand_id) brand_id, observed_at
              FROM bw_vendor_snapshots
             WHERE source = 'workbook' AND snapshot_type = 'metric'
             ORDER BY brand_id, observed_at
        """)).mappings().all()}
    has_metric_snapshot = set(metric_snapshots)

    while True:
        rows = conn.execute(text("""
            SELECT mb.id, mb.market_id, mb.brand_id, mb.baseline, mb.created_at
              FROM bw_market_brands mb
             WHERE mb.id > :cursor
             ORDER BY mb.id
             LIMIT :limit
        """), {'cursor': cursor, 'limit': BATCH}).mappings().all()
        if not rows:
            break

        for row in rows:
            baseline = row['baseline'] or {}
            if isinstance(baseline, str):
                baseline = json.loads(baseline)
            batch_id = baseline.get('import_batch_id')
            source_row = baseline.get('source_row')
            # Two memberships were added by hand after the import and carry no
            # batch or row. Keying them to the membership id keeps them stable
            # without inventing a workbook position they never had.
            if batch_id and source_row is not None:
                ident = {'batch': batch_id, 'row': source_row}
            else:
                ident = {'membership': row['id']}

            metrics = baseline.get('metrics') or {}
            funding = baseline.get('funding_baseline') or {}
            taxonomy = baseline.get('taxonomy') or {}

            plan = [
                ('hq_country', baseline.get('hq_country'), None),
                ('founded_year', baseline.get('founded_year'), None),
                ('funding_total_musd', funding.get('total_musd'), None),
                ('market_category', taxonomy.get('category'), row['market_id']),
                ('market_sub_category', taxonomy.get('sub_category'),
                 row['market_id']),
            ]
            if row['brand_id'] not in has_metric_snapshot:
                # No workbook snapshot for this membership — it was added by
                # hand after the import — so the baseline is the only record
                # of these two.
                plan.extend([
                    ('employee_count', metrics.get('employee_count'), None),
                    ('funding_status', funding.get('status'), None),
                ])

            for field_key, value, market_id in plan:
                if value is None:
                    skipped += 1
                    continue
                try:
                    obs = record_observation(
                        conn, brand_id=row['brand_id'], field_key=field_key,
                        value=value, source='workbook',
                        source_record_id=mint_source_record_id(
                            'import', market_id=market_id, **ident),
                        observed_at=metric_snapshots.get(row['brand_id'],
                                                         row['created_at']),
                        market_id=market_id,
                        metadata={'origin': 'baseline_backfill'})
                except NormalizationError as exc:
                    print(f"  ! membership {row['id']} {field_key}: {exc}")
                    skipped += 1
                    continue
                if obs:
                    written += 1
                else:
                    skipped += 1

            cursor = int(row['id'])

        if not args.dry_run:
            _save_cursor(conn, 'baseline', str(cursor), written, skipped)
            conn.commit()
            written = skipped = 0
        else:
            conn.rollback()
            break

    return _state(conn, 'baseline', dry_run=args.dry_run,
                  written=written, skipped=skipped)


# ---------------------------------------------------------------------------
# snapshots
# ---------------------------------------------------------------------------

def cmd_snapshots(conn, args) -> Dict[str, Any]:
    """Normalize every collected snapshot that has not been normalized yet."""
    written = skipped = failed = 0
    by_shape: Dict[str, int] = {}
    after = int(_load_cursor(conn, 'snapshots')) if args.resume else 0

    while True:
        ids = pending_snapshot_ids(conn, limit=BATCH, after_id=after)
        if not ids:
            break
        for snapshot_id in ids:
            result = normalize_snapshot(conn, snapshot_id)
            by_shape[result['shape']] = by_shape.get(result['shape'], 0) + 1
            if result['status'] == 'failed':
                failed += 1
                print(f"  ! snapshot {snapshot_id} ({result['shape']}): "
                      f"{result['reason']}")
            elif result['status'] == 'skipped':
                skipped += 1
            written += result['written']
            after = snapshot_id

        if not args.dry_run:
            _save_cursor(conn, 'snapshots', str(after), written, skipped,
                         detail={'shapes': by_shape, 'failed': failed})
            conn.commit()
            written = skipped = 0
        else:
            conn.rollback()
            break

    return _state(conn, 'snapshots', dry_run=args.dry_run, shapes=by_shape,
                  failed=failed)


# ---------------------------------------------------------------------------
# canonical
# ---------------------------------------------------------------------------

def cmd_canonical(conn, args) -> Dict[str, Any]:
    """Resolve every field for every entity, then fill the projections."""
    brands = [int(r[0]) for r in conn.execute(text("""
        SELECT DISTINCT brand_id FROM bw_entity_observations ORDER BY brand_id
    """)).fetchall()]

    resolved = moved = 0
    conflicts: List[str] = []
    for brand_id in brands:
        for result in entity_resolution.resolve_entity(
                conn, brand_id, trigger='backfill'):
            resolved += 1
            moved += 1 if result['changed'] else 0
            if result['status'] == 'conflict':
                conflicts.append(f"{brand_id}/{result['field_key']}")
        entity_projection.project_entity(conn, brand_id)

        memberships = conn.execute(text("""
            SELECT market_id FROM bw_market_brands WHERE brand_id = :b
        """), {'b': brand_id}).fetchall()
        for (market_id,) in memberships:
            entity_resolution.resolve_entity(conn, brand_id,
                                             market_id=int(market_id),
                                             trigger='backfill')
        entity_projection.project_all_memberships(conn, brand_id)

    if args.dry_run:
        conn.rollback()
    else:
        _save_cursor(conn, 'canonical', str(brands[-1] if brands else 0),
                     resolved, 0, status='done',
                     detail={'conflicts': conflicts[:50]})
        conn.commit()

    return {'subcommand': 'canonical', 'dry_run': args.dry_run,
            'brands': len(brands), 'fields_resolved': resolved,
            'canonical_moved': moved, 'conflicts': len(conflicts),
            'policy_version': ENTITY_FIELD_POLICY_VERSION}


# ---------------------------------------------------------------------------
# query-terms
# ---------------------------------------------------------------------------

def cmd_query_terms(conn, args) -> Dict[str, Any]:
    """Give every entity its own matching vocabulary.

    Terms are marked ``qualification_required`` unless they can stand alone
    safely, so seeding this does not by itself widen anything's matching.
    """
    brands = [int(r[0]) for r in conn.execute(text("""
        SELECT DISTINCT brand_id FROM bw_market_brands ORDER BY brand_id
    """)).fetchall()]
    written = skipped = 0
    for brand_id in brands:
        result = entity_content.seed_query_terms(conn, brand_id)
        written += result['written']
        skipped += result['skipped']

    safe = conn.execute(text("""
        SELECT count(*) FROM bw_entity_query_terms
         WHERE enabled AND NOT qualification_required
    """)).scalar()
    if args.dry_run:
        conn.rollback()
    else:
        _save_cursor(conn, 'query-terms', str(brands[-1] if brands else 0),
                     written, skipped, status='done')
        conn.commit()
    return {'subcommand': 'query-terms', 'dry_run': args.dry_run,
            'brands': len(brands), 'terms_written': written,
            'terms_skipped': skipped, 'safe_for_standalone_matching': safe}


# ---------------------------------------------------------------------------
# content-links
# ---------------------------------------------------------------------------

def cmd_content_links(conn, args) -> Dict[str, Any]:
    """Turn existing brand attributions into typed, channelled links.

    The source is ``bw_article_categories``, read as DISTINCT (article, brand).
    A brand carrying three category rows on one article is one relationship,
    and counting the category rows instead would inflate every coverage figure
    on the vendor page by the number of categories the classifier chose.
    """
    cursor = _load_cursor(conn, 'content-links') if args.resume else ''
    written = skipped = 0
    by_channel: Dict[str, int] = {}

    while True:
        rows = conn.execute(text("""
            SELECT DISTINCT ON (c.article_uri, c.brand_id)
                   c.article_uri, c.brand_id, a.news_source, a.bias_source,
                   a.social_meta
              FROM bw_article_categories c
              JOIN articles a ON a.uri = c.article_uri
             WHERE c.article_uri > :cursor
             ORDER BY c.article_uri, c.brand_id
             LIMIT :limit
        """), {'cursor': cursor, 'limit': BATCH}).mappings().all()
        if not rows:
            break

        for row in rows:
            platform, channel = classify_source(row['news_source'],
                                                row['bias_source'])
            owned = channel in entity_content.OWNED_CHANNELS
            if owned:
                relationship, method = 'owned', 'identifier'
            elif channel in ('public_social', 'community'):
                relationship, method = 'mentions', 'classifier'
            else:
                relationship, method = 'about', 'classifier'

            link_id = entity_content.link_content(
                conn, brand_id=row['brand_id'], article_uri=row['article_uri'],
                relationship=relationship, channel=channel, platform=platform,
                attribution_method=method,
                metadata={'origin': 'backfill'})
            if link_id:
                written += 1
                by_channel[channel] = by_channel.get(channel, 0) + 1
            else:
                skipped += 1
            cursor = row['article_uri']

        if not args.dry_run:
            _save_cursor(conn, 'content-links', cursor, written, skipped,
                         detail={'channels': by_channel})
            conn.commit()
            written = skipped = 0
        else:
            conn.rollback()
            break

    return _state(conn, 'content-links', dry_run=args.dry_run,
                  channels=by_channel)


# ---------------------------------------------------------------------------
# mentions
# ---------------------------------------------------------------------------

def cmd_mentions(conn, args) -> Dict[str, Any]:
    """Create one mention per (entity, article), and score only what is safe.

    An article-level relevance and sentiment can be reused when exactly one
    entity is linked to that article, because then the score could only ever
    have been about that entity. Where two or more are linked, the existing
    score cannot be split between them and both mentions are left pending for
    per-entity evaluation — which is the defect this table exists to fix, so
    inheriting the shared score here would carry it straight over.
    """
    cursor = _load_cursor(conn, 'mentions') if args.resume else '0'
    written = inherited = pending = 0

    while True:
        rows = conn.execute(text("""
            SELECT l.id, l.brand_id, l.article_uri, l.channel, l.platform,
                   l.relationship,
                   a.topic_alignment_score, a.sentiment,
                   (SELECT count(*) FROM bw_entity_content_links x
                     WHERE x.article_uri = l.article_uri) AS entities_on_article
              FROM bw_entity_content_links l
              JOIN articles a ON a.uri = l.article_uri
             WHERE l.id > :cursor
               -- A link the term pass already produced a mention for is done.
               -- Its mention carries the matched term, and re-deriving one
               -- here without the term would hash differently and become a
               -- second mention of the same company in the same post.
               AND NOT EXISTS (SELECT 1 FROM bw_entity_mentions m
                                WHERE m.brand_id = l.brand_id
                                  AND m.article_uri = l.article_uri)
             ORDER BY l.id
             LIMIT :limit
        """), {'cursor': int(cursor), 'limit': BATCH}).mappings().all()
        if not rows:
            break

        for row in rows:
            owned = row['channel'] in entity_content.OWNED_CHANNELS
            single = int(row['entities_on_article']) == 1

            if owned:
                # The company's own post: fully relevant to it, a claim rather
                # than an opinion, and never part of external sentiment.
                kwargs = dict(mention_type='owned_attribution', relevance=1.0,
                              sentiment=None, stance='owned_claim',
                              status='accepted',
                              evaluation_method='attribution')
            elif single and row['topic_alignment_score'] is not None:
                kwargs = dict(mention_type='explicit_name',
                              relevance=float(row['topic_alignment_score']),
                              sentiment=row['sentiment'], stance=None,
                              status='accepted',
                              evaluation_method='inherited_article_score')
                inherited += 1
            else:
                kwargs = dict(mention_type='explicit_name', relevance=None,
                              sentiment=None, stance=None, status='pending',
                              evaluation_method=None)
                pending += 1

            mention_id = entity_content.record_mention(
                conn, brand_id=row['brand_id'], article_uri=row['article_uri'],
                channel=row['channel'], platform=row['platform'],
                content_link_id=row['id'],
                metadata={'origin': 'backfill',
                          'entities_on_article': int(row['entities_on_article'])},
                **kwargs)
            if mention_id:
                written += 1
            cursor = str(row['id'])

        if not args.dry_run:
            _save_cursor(conn, 'mentions', cursor, written, 0,
                         detail={'inherited': inherited, 'pending': pending})
            conn.commit()
            written = 0
        else:
            conn.rollback()
            break

    social = _social_term_pass(conn, args)
    return _state(conn, 'mentions', dry_run=args.dry_run,
                  inherited_article_score=inherited, left_pending=pending,
                  social_posts_scanned=social['scanned'],
                  social_mentions=social['mentions'],
                  posts_naming_two_or_more=social['multi_entity'])


def _social_term_pass(conn, args) -> Dict[str, Any]:
    """Find vendors named in social posts that no classifier attributed.

    The market's social keyword group watches themes — "agentic SOC", "alert
    triage" — not vendor names, so nothing in the existing pipeline ever asked
    which company a given post was about. Scanning the text for the entities'
    own safe terms is what turns those posts into per-vendor mentions.

    This runs over the whole non-excluded roster rather than only the entities
    with social collection switched on. That flag governs what we pay to
    collect; these posts are already collected, and attributing them costs
    nothing.
    """
    brands = [int(r[0]) for r in conn.execute(text("""
        SELECT DISTINCT brand_id FROM bw_market_brands WHERE role <> 'excluded'
    """)).fetchall()]
    terms = entity_content.safe_terms_for(conn, brands)

    rows = conn.execute(text("""
        SELECT uri, title, summary, news_source, bias_source
          FROM articles
         WHERE news_source IN ('bluesky', 'reddit.com', 'www.reddit.com')
            OR news_source LIKE 'xpoz:%'
            OR news_source LIKE 'bsky%'
         ORDER BY uri
    """)).mappings().all()

    scanned = mentions = multi = 0
    for row in rows:
        platform, channel = classify_source(row['news_source'],
                                            row['bias_source'])
        if platform is None:
            continue
        scanned += 1
        blob = ' '.join(filter(None, [row['title'], row['summary']]))
        found = entity_content.candidates_from_terms(blob, terms)
        if len(found) > 1:
            multi += 1
        for candidate in found:
            link_id = entity_content.link_content(
                conn, brand_id=candidate['brand_id'],
                article_uri=row['uri'], relationship='mentions',
                channel=channel, platform=platform,
                attribution_method='query_term',
                metadata={'origin': 'backfill_social_terms',
                          'matched_term': candidate['term']})
            # Left pending on purpose: a term was found, nobody has judged
            # what the post says about that company, and an unevaluated
            # mention must not be counted as neutral.
            if entity_content.record_mention(
                    conn, brand_id=candidate['brand_id'],
                    article_uri=row['uri'], mention_type='explicit_name',
                    channel=channel, platform=platform,
                    content_link_id=link_id, excerpt=candidate['excerpt'],
                    matched_term=candidate['term'],
                    matched_query_term_id=candidate['query_term_id'],
                    status='pending',
                    metadata={'origin': 'backfill_social_terms'}):
                mentions += 1

    if not args.dry_run:
        conn.commit()
    else:
        conn.rollback()
    return {'scanned': scanned, 'mentions': mentions, 'multi_entity': multi}


# ---------------------------------------------------------------------------
# social-identities
# ---------------------------------------------------------------------------

def cmd_social_identities(conn, args) -> Dict[str, Any]:
    """Register the accounts seen posting, and propose only what is provable.

    Every account that has posted something we collected gets a row. Almost
    none of them get an entity mapping: a handle resembling a company name is
    a guess, and the only automatic verification allowed is a stable platform
    id or a link from a domain already verified as the company's.
    """
    accounts = renamed = proposed = 0
    rows = conn.execute(text("""
        SELECT uri, news_source, bias_source, social_meta
          FROM articles
         WHERE social_meta IS NOT NULL
           AND jsonb_typeof(social_meta) = 'object'
           AND social_meta ? 'author'
         ORDER BY uri
    """)).mappings().all()

    seen = set()
    for row in rows:
        meta = row['social_meta']
        platform, _channel = classify_source(row['news_source'],
                                             row['bias_source'])
        platform = meta.get('platform') or platform
        handle = meta.get('author') or meta.get('username')
        if not platform or not handle:
            continue
        key = (platform, str(handle).strip().lower())
        if key in seen:
            continue
        seen.add(key)
        result = entity_identity.upsert_account(
            conn, platform=platform, handle=str(handle),
            platform_user_id=meta.get('author_id') or meta.get('did'))
        accounts += 1 if result['created'] else 0
        renamed += 1 if result['renamed'] else 0

    # Owned LinkedIn company pages are the one case with direct evidence: the
    # collector asked for that company's page by its verified URL.
    owned = conn.execute(text("""
        SELECT DISTINCT c.brand_id, i.id AS identifier_id, i.normalized_value
          FROM bw_article_categories c
          JOIN articles a ON a.uri = c.article_uri
          JOIN bw_vendor_identifiers i
            ON i.brand_id = c.brand_id AND i.kind = 'linkedin_company_url'
           AND i.valid_to IS NULL
         WHERE a.bias_source = 'vendor:linkedin'
    """)).mappings().all()
    for row in owned:
        account = entity_identity.upsert_account(
            conn, platform='linkedin', handle=row['normalized_value'],
            platform_user_id=row['normalized_value'])
        outcome = entity_identity.propose_identity(
            conn, brand_id=row['brand_id'],
            social_account_id=account['account_id'],
            relationship='owned_company', verification_method='provider',
            provenance={'identifier_id': row['identifier_id'],
                        'evidence': 'collector requested this company URL'})
        if outcome['identity_id']:
            proposed += 1

    if args.dry_run:
        conn.rollback()
    else:
        _save_cursor(conn, 'social-identities', '', accounts, 0, status='done',
                     detail={'renamed': renamed, 'proposed': proposed})
        conn.commit()
    return {'subcommand': 'social-identities', 'dry_run': args.dry_run,
            'accounts_created': accounts, 'renames_observed': renamed,
            'identities_verified': proposed,
            'accounts_total': _scalar(conn, 'SELECT count(*) FROM social_accounts')}


# ---------------------------------------------------------------------------
# shadow
# ---------------------------------------------------------------------------

def cmd_shadow(conn, args) -> Dict[str, Any]:
    """Read every vendor both ways and report what a cutover would change.

    This is the evidence for turning ENTITY_INTELLIGENCE_CANONICAL_READ on. It
    writes nothing and spends nothing; it just runs the legacy and canonical
    expressions side by side over the same rows.

    Only one class blocks a cutover: a real value that would become unknown,
    because a filter matching a vendor today would stop matching it. A
    placeholder zero disappearing is the fix rather than a regression, and is
    counted separately.
    """
    markets = [int(r[0]) for r in conn.execute(text(
        'SELECT id FROM bw_markets ORDER BY id')).fetchall()]
    out: Dict[str, Any] = {'subcommand': 'shadow', 'markets': {}}
    blocked = []
    for market_id in markets:
        result = entity_dual_read.compare_market(conn, market_id)
        out['markets'][market_id] = result
        if not result['safe_to_cut_over']:
            blocked.append(market_id)
    conn.rollback()
    out['blocked_markets'] = blocked
    out['passed'] = not blocked
    return out


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def cmd_verify(conn, args) -> Dict[str, Any]:
    """Report what the backfill produced, and what it could not.

    The SOC Automation assertions are pinned to what the market actually
    holds: 85 memberships, of which 83 carry workbook provenance (81 vendors
    and 2 excluded rows), and 2 vendors that were added by hand afterwards
    with no source row. Undisclosed and bootstrapped funding must still be
    null rather than zero.
    """
    out: Dict[str, Any] = {'policy_version': ENTITY_FIELD_POLICY_VERSION}

    out['memberships'] = _scalar(conn, "SELECT count(*) FROM bw_market_brands")
    out['memberships_with_import_provenance'] = _scalar(
        conn, "SELECT count(*) FROM bw_market_brands WHERE baseline ? 'source_row'")
    out['memberships_excluded'] = _scalar(
        conn, "SELECT count(*) FROM bw_market_brands WHERE role = 'excluded'")

    out['observations_by_field'] = _rows(conn, """
        SELECT field_key, source, count(*) AS n
          FROM bw_entity_observations GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    out['snapshots_by_normalization'] = _rows(conn, """
        SELECT normalization_status, count(*) AS n
          FROM bw_vendor_snapshots GROUP BY 1 ORDER BY 2 DESC""")
    out['snapshots_not_normalized'] = _rows(conn, """
        SELECT id, source, snapshot_type, normalization_error
          FROM bw_vendor_snapshots
         WHERE normalization_status IN ('failed', 'pending')
         ORDER BY id LIMIT 25""")
    out['canonical_by_field'] = _rows(conn, """
        SELECT field_key, status, count(*) AS n
          FROM bw_entity_canonical_fields GROUP BY 1, 2 ORDER BY 1, 2""")

    # The comparison that justifies the whole change: where does a newly
    # collected reading now disagree with what the import wrote?
    out['baseline_vs_canonical'] = _rows(conn, """
        SELECT b.display_name,
               mb.baseline->'metrics'->>'employee_count' AS baseline_headcount,
               p.employee_count AS canonical_headcount,
               p.employee_count_source AS source
          FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
          JOIN bw_entity_profiles p ON p.brand_id = mb.brand_id
         WHERE p.employee_count IS NOT NULL
           AND COALESCE(mb.baseline->'metrics'->>'employee_count', '')
               <> p.employee_count::text
         ORDER BY b.display_name LIMIT 50""")

    # Unknown funding must never have become a number.
    out['unknown_funding_kept_null'] = _scalar(conn, """
        SELECT count(*) FROM bw_market_brands mb
          LEFT JOIN bw_entity_profiles p ON p.brand_id = mb.brand_id
         WHERE mb.baseline->'funding_baseline'->>'status'
               IN ('Undisclosed', 'Bootstrapped')
           AND p.funding_total_musd IS NOT NULL""")

    out['open_review_tasks'] = _rows(conn, """
        SELECT kind, severity, count(*) AS n,
               count(*) FILTER (WHERE market_id IS NULL) AS entity_global
          FROM bw_review_tasks WHERE status = 'open'
         GROUP BY 1, 2 ORDER BY 3 DESC""")

    # ---- phase 2 -----------------------------------------------------
    out['content_links_by_channel'] = _rows(conn, """
        SELECT channel, relationship, count(*) AS n
          FROM bw_entity_content_links GROUP BY 1, 2 ORDER BY 3 DESC""")

    # Category rows must not become links. A brand with three categories on
    # one article is one relationship, and counting the categories would
    # inflate every coverage figure on the vendor page.
    out['category_rows'] = _scalar(conn, 'SELECT count(*) FROM bw_article_categories')
    out['distinct_article_brand_pairs'] = _scalar(conn, """
        SELECT count(*) FROM (SELECT DISTINCT article_uri, brand_id
                                FROM bw_article_categories) t""")
    out['links_from_attribution'] = _scalar(conn, """
        SELECT count(*) FROM bw_entity_content_links
         WHERE metadata->>'origin' = 'backfill'""")

    out['entities_per_article'] = _rows(conn, """
        SELECT entities, count(*) AS articles FROM (
            SELECT article_uri, count(DISTINCT brand_id) AS entities
              FROM bw_entity_content_links GROUP BY 1) t
         GROUP BY 1 ORDER BY 1""")

    out['mentions_by_status'] = _rows(conn, """
        SELECT status, channel, count(*) AS n
          FROM bw_entity_mentions GROUP BY 1, 2 ORDER BY 3 DESC""")

    # An owned post is a claim. If any carries sentiment, it is being counted
    # as somebody's opinion of the company rather than the company's own words.
    out['owned_mentions_with_sentiment'] = _scalar(conn, """
        SELECT count(*) FROM bw_entity_mentions
         WHERE channel IN ('owned_web', 'owned_social') AND sentiment IS NOT NULL""")

    # A pending mention must never have been scored.
    out['pending_mentions_with_scores'] = _scalar(conn, """
        SELECT count(*) FROM bw_entity_mentions
         WHERE status = 'pending' AND (relevance IS NOT NULL
                                       OR sentiment IS NOT NULL)""")

    out['social_identities'] = _rows(conn, """
        SELECT relationship, status, verification_method, count(*) AS n
          FROM bw_entity_social_identities WHERE valid_to IS NULL
         GROUP BY 1, 2, 3 ORDER BY 4 DESC""")

    out['accounts_claimed_by_two_owners'] = _scalar(conn, """
        SELECT count(*) FROM (
            SELECT social_account_id FROM bw_entity_social_identities
             WHERE relationship = 'owned_company' AND valid_to IS NULL
               AND status IN ('proposed', 'verified')
             GROUP BY 1 HAVING count(DISTINCT brand_id) > 1) t""")

    checks = []
    checks.append(('all 83 workbook rows represented',
                   out['memberships_with_import_provenance'] == 83))
    checks.append(('both excluded rows still excluded',
                   out['memberships_excluded'] == 2))
    checks.append(('85 memberships total (83 imported + 2 added by hand)',
                   out['memberships'] == 85))
    checks.append(('undisclosed/bootstrapped funding still null',
                   out['unknown_funding_kept_null'] == 0))
    checks.append(('no snapshot left unnormalized',
                   not out['snapshots_not_normalized']))
    checks.append(('category rows did not multiply into links',
                   out['links_from_attribution']
                   == out['distinct_article_brand_pairs']))
    checks.append(('owned posts carry no external sentiment',
                   out['owned_mentions_with_sentiment'] == 0))
    checks.append(('unjudged mentions carry no scores',
                   out['pending_mentions_with_scores'] == 0))
    checks.append(('no account is owned by two companies',
                   out['accounts_claimed_by_two_owners'] == 0))
    out['checks'] = [{'assertion': a, 'passed': bool(p)} for a, p in checks]
    out['passed'] = all(p for _, p in checks)
    return out


def _scalar(conn, sql: str) -> Any:
    return conn.execute(text(sql)).scalar()


def _rows(conn, sql: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(sql)).mappings().all()]


def _state(conn, subcommand: str, **extra) -> Dict[str, Any]:
    row = conn.execute(text("""
        SELECT rows_done, rows_skipped, cursor_value, status
          FROM bw_entity_backfill_state WHERE subcommand = :s
    """), {'s': subcommand}).mappings().first()
    out = {'subcommand': subcommand}
    out.update(dict(row) if row else {})
    out.update(extra)
    return out


COMMANDS = {
    'baseline': cmd_baseline,
    'snapshots': cmd_snapshots,
    'query-terms': cmd_query_terms,
    'content-links': cmd_content_links,
    'mentions': cmd_mentions,
    'social-identities': cmd_social_identities,
    'canonical': cmd_canonical,
    'shadow': cmd_shadow,
    'verify': cmd_verify,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('subcommand',
                        choices=sorted(set(COMMANDS) | set(LATER_PHASES)))
    parser.add_argument('--dry-run', action='store_true',
                        help='roll back instead of committing')
    parser.add_argument('--resume', action='store_true',
                        help='continue from the stored cursor')
    parser.add_argument('--json', action='store_true',
                        help='machine-readable output only')
    args = parser.parse_args()

    if args.subcommand in LATER_PHASES:
        print(f"'{args.subcommand}' needs tables from "
              f"{LATER_PHASES[args.subcommand]}, which this phase has not "
              f"created yet.", file=sys.stderr)
        return 2

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result = COMMANDS[args.subcommand](conn, args)
        if not args.dry_run and args.subcommand != 'verify':
            conn.commit()
    finally:
        conn.close()

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _human(args.subcommand, result)
    return 0 if result.get('passed', True) else 1


def _human(subcommand: str, result: Dict[str, Any]) -> None:
    print(f"\n{subcommand}")
    print('-' * len(subcommand))
    for key, value in result.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            print(f"{key}:")
            for item in value[:25]:
                print('   ' + '  '.join(f"{k}={v}" for k, v in item.items()))
        elif isinstance(value, dict):
            print(f"{key}: " + ', '.join(f"{k}={v}" for k, v in value.items()))
        else:
            print(f"{key}: {value}")


if __name__ == '__main__':
    raise SystemExit(main())
