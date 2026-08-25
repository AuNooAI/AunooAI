"""The one hook every collector calls after its own writes have landed.

Collectors keep doing exactly what they do: fetch, store a snapshot or an
article, close a run. This service runs afterwards and turns what landed into
entity records — observations, content links, mentions, accounts.

The ordering rule is the important part. The provider's data is already durable
when this runs, and nothing here is allowed to undo it. If normalization fails,
the snapshot stays, is marked ``failed``, and the run closes ``partial`` so it
can be retried without paying the provider again. A processing bug must never
cost collected data, because the collection is the expensive half.

No model is called inside a transaction that holds provider data either.
Finding a mention is cheap and deterministic and happens here; judging it costs
money and latency and happens later, off the ingest path.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import text

from app.services import (
    entity_content, entity_identity, entity_projection, entity_resolution,
)
from app.services.entity_observations import (
    NormalizationError, normalize_snapshot as _normalize_snapshot,
)
from app.services.social_sources import classify_source

logger = logging.getLogger(__name__)

# Relationship for each channel when the entity is the one that published it.
_OWNED_CHANNELS = {'owned_web', 'owned_social'}


def normalize_snapshot(conn, snapshot_id: int) -> Dict[str, Any]:
    """Normalize one snapshot into observations. Never raises for bad data."""
    try:
        return _normalize_snapshot(conn, snapshot_id)
    except NormalizationError as exc:
        logger.warning('snapshot_id=%s normalization refused: %s',
                       snapshot_id, exc)
        return {'snapshot_id': snapshot_id, 'status': 'failed',
                'reason': str(exc), 'written': 0, 'fields': []}


def link_content(conn, article_uri: str,
                 candidates: Optional[List[Dict[str, Any]]] = None,
                 context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Relate one article to every entity it belongs to.

    ``candidates`` may be supplied by a caller that already knows — the
    LinkedIn collector requested a specific company's page, so it does not need
    to guess. When it is omitted, the entity is worked out from the article's
    own attribution and from the entity query terms found in its text.
    """
    context = context or {}
    article = conn.execute(text("""
        SELECT uri, title, summary, news_source, bias_source, social_meta
          FROM articles WHERE uri = :u
    """), {'u': article_uri}).mappings().first()
    if not article:
        return {'article_uri': article_uri, 'links': 0, 'mentions': 0,
                'status': 'missing'}

    platform, channel = classify_source(article['news_source'],
                                        article['bias_source'])
    result = {'article_uri': article_uri, 'platform': platform,
              'channel': channel, 'links': 0, 'mentions': 0,
              'brands': [], 'status': 'ok'}

    account_id = _account_for(conn, article, platform)

    if candidates is None:
        candidates = _discover_candidates(conn, article, channel)

    # Social lanes are gated separately from the rest of the layer, because
    # they are the expensive half: term matching over public posts feeds a
    # model-scored evaluation queue. Off means public posts are not turned
    # into mentions at all; owned and earned content is unaffected.
    from app.services import entity_flags

    if (channel in ('public_social', 'community')
            and not entity_flags.social_enabled()):
        result['status'] = 'skipped: social lanes disabled'
        return result

    owned = channel in _OWNED_CHANNELS
    for candidate in candidates:
        brand_id = int(candidate['brand_id'])
        relationship = candidate.get('relationship') or (
            'owned' if owned else 'mentions')
        link_id = entity_content.link_content(
            conn, brand_id=brand_id, article_uri=article_uri,
            relationship=relationship, channel=channel, platform=platform,
            social_account_id=account_id,
            attribution_method=candidate.get('attribution_method', 'query_term'),
            confidence=candidate.get('confidence'),
            collection_run_id=context.get('collection_run_id'),
            metadata={'matched_term': candidate.get('term')})
        result['links'] += 1
        result['brands'].append(brand_id)

        # An owned post proves the company said something. It is a claim, it is
        # fully relevant to them, and it is not somebody else's opinion of
        # them, so it is scored here rather than queued for a model.
        if owned:
            mention_id = entity_content.record_mention(
                conn, brand_id=brand_id, article_uri=article_uri,
                mention_type='owned_attribution', channel=channel,
                platform=platform, content_link_id=link_id,
                matched_term=candidate.get('term'),
                matched_query_term_id=candidate.get('query_term_id'),
                relevance=1.0, sentiment=None, stance='owned_claim',
                status='accepted', evaluation_method='attribution')
        else:
            mention_id = entity_content.record_mention(
                conn, brand_id=brand_id, article_uri=article_uri,
                mention_type=candidate.get('mention_type', 'explicit_name'),
                channel=channel, platform=platform, content_link_id=link_id,
                excerpt=candidate.get('excerpt'),
                matched_term=candidate.get('term'),
                matched_query_term_id=candidate.get('query_term_id'),
                status='pending')
        if mention_id:
            result['mentions'] += 1
    return result


def _account_for(conn, article, platform: Optional[str]) -> Optional[int]:
    """The posting account, when the row carries one.

    ``social_meta`` is a JSON scalar null on most Bluesky rows in this tenant,
    so the type is checked rather than assumed.
    """
    meta = article['social_meta']
    if not isinstance(meta, dict) or not platform:
        return None
    handle = meta.get('author') or meta.get('username')
    if not handle:
        return None
    account = entity_identity.upsert_account(
        conn, platform=meta.get('platform') or platform, handle=str(handle),
        platform_user_id=meta.get('author_id') or meta.get('did'))
    return account['account_id']


def _discover_candidates(conn, article, channel: str) -> List[Dict[str, Any]]:
    """Work out which entities an article is about.

    Three routes, most trustworthy first: an existing Brand Watcher
    attribution, the keyword monitor's own match records, and finally the
    entity's safe query terms found in the text.
    """
    attributed = conn.execute(text("""
        SELECT DISTINCT brand_id FROM bw_article_categories WHERE article_uri = :u
    """), {'u': article['uri']}).fetchall()
    if attributed:
        return [{'brand_id': int(r[0]), 'attribution_method': 'classifier',
                 'mention_type': 'explicit_name'} for r in attributed]

    by_keyword = entity_content.candidates_from_keywords(conn, article['uri'])
    if by_keyword:
        return [{'brand_id': c['brand_id'], 'query_term_id': c['query_term_id'],
                 'term': c['term'], 'attribution_method': 'keyword',
                 'mention_type': _mention_type(c['term_kind'])}
                for c in by_keyword]

    blob = ' '.join(filter(None, [article['title'], article['summary']]))
    if not blob:
        return []
    terms = entity_content.safe_terms_for(
        conn, _enabled_social_brands(conn) if channel in
        ('public_social', 'community') else _all_brands(conn))
    return [{'brand_id': c['brand_id'], 'query_term_id': c['query_term_id'],
             'term': c['term'], 'excerpt': c['excerpt'],
             'attribution_method': 'query_term',
             'mention_type': _mention_type(c['term_kind'])}
            for c in entity_content.candidates_from_terms(blob, terms)]


def _mention_type(term_kind: str) -> str:
    return {'name': 'explicit_name', 'alias': 'alias', 'former_name': 'alias',
            'product': 'product', 'person': 'person',
            'handle': 'handle'}.get(term_kind, 'explicit_name')


def _enabled_social_brands(conn) -> List[int]:
    """Only entities an operator has switched social collection on for."""
    rows = conn.execute(text("""
        SELECT DISTINCT brand_id FROM bw_market_brands
         WHERE social_collection_enabled AND role <> 'excluded'
    """)).fetchall()
    return [int(r[0]) for r in rows]


def _all_brands(conn) -> List[int]:
    rows = conn.execute(text("""
        SELECT DISTINCT brand_id FROM bw_market_brands WHERE role <> 'excluded'
    """)).fetchall()
    return [int(r[0]) for r in rows]


def _advance_requested_policies(conn, run_id: int, status: str) -> None:
    """Move the claimed vendors on, or back them off, by the run's outcome.

    Its own savepoint: this is bookkeeping, and a fault in it must not abort
    the transaction holding the provider rows.
    """
    from app.services import entity_scheduler as sch

    point = conn.begin_nested()
    try:
        row = conn.execute(text("""
            SELECT source, requested_brand_ids FROM bw_collection_runs
             WHERE id = :r
        """), {'r': run_id}).mappings().first()
        if not row or not row['requested_brand_ids']:
            point.rollback()
            return
        ids = [int(b) for b in row['requested_brand_ids']]
        if status in ('succeeded', 'partial'):
            sch.record_success(conn, row['source'], ids)
        else:
            sch.record_failure(conn, row['source'], ids,
                               error=f'run closed {status}')
        point.commit()
    except Exception:                                       # noqa: BLE001
        point.rollback()
        logger.warning('could not advance vendor policies for run_id=%s', run_id)


def process_pending(conn, run_id: Optional[int] = None,
                    snapshot_limit: int = 200,
                    article_limit: int = 200) -> Dict[str, Any]:
    """Process whatever collection has left waiting, and nothing else.

    This is the hook every collector reaches through ``close_run``. It works
    off durable backlog markers rather than off what a particular run happened
    to write, which is what makes it self-healing: a snapshot stranded by a
    crash, a deploy, or a normalizer bug is still ``pending`` afterwards and
    the next run of any source picks it up. Keying the work to one run id
    would strand exactly the rows that most need retrying.

    Both halves are bounded. Closing a collection run must stay a fast ledger
    write, so a large backlog drains over several runs instead of turning one
    run's completion into an unbounded job.
    """
    summary = {'run_id': run_id, 'snapshots': 0, 'normalized': 0,
               'observations': 0, 'failed': 0, 'retried': 0, 'articles': 0,
               'links': 0, 'mentions': 0, 'resolved_brands': 0}
    touched: set = set()

    # 'failed' as well as 'pending'. The normalizer marks a payload it could
    # not map as failed, and selecting only pending meant those rows were
    # never looked at again — the comment claimed they were retried and they
    # were not. A malformed snapshot usually stays malformed, so the count is
    # reported on the run rather than being retried silently forever.
    pending = conn.execute(text("""
        SELECT id, brand_id, normalization_status FROM bw_vendor_snapshots
         WHERE normalization_status IN ('pending', 'failed')
         ORDER BY (normalization_status = 'failed'), id
         LIMIT :lim
    """), {'lim': snapshot_limit}).mappings().all()

    for row in pending:
        summary['snapshots'] += 1
        if row['normalization_status'] == 'failed':
            summary['retried'] += 1
        outcome = normalize_snapshot(conn, int(row['id']))
        if outcome['status'] == 'failed':
            summary['failed'] += 1
            continue
        if outcome['status'] in ('normalized', 'partial'):
            summary['normalized'] += 1
            summary['observations'] += outcome.get('written', 0)
            if row['brand_id']:
                touched.add(int(row['brand_id']))

    # Articles with no entity relationship yet, from **both** places they
    # land. Brand Watcher attributes articles into bw_article_categories;
    # the market keyword group and the vendor RSS feeds land theirs in
    # bw_market_articles and are never attributed to a company at all.
    # Reading only the first meant the entire market news corpus — over a
    # thousand articles, growing by a hundred a day — never became a content
    # link, so a vendor's page showed firmographics and no coverage.
    # An article we have already examined is skipped even when it matched
    # nothing. Asking only for articles with no content link meant the ones
    # that name no vendor — most of a news corpus — were re-scanned on every
    # run and the backlog never drained: 2,400 examinations produced twelve
    # links, the same few hundred articles going round.
    unlinked = conn.execute(text("""
        SELECT article_uri FROM (
            SELECT DISTINCT c.article_uri FROM bw_article_categories c
            UNION
            SELECT DISTINCT m.article_uri FROM bw_market_articles m
        ) candidates
         WHERE NOT EXISTS (SELECT 1 FROM bw_entity_content_links l
                            WHERE l.article_uri = candidates.article_uri)
           AND NOT EXISTS (SELECT 1 FROM bw_entity_link_attempts a
                            WHERE a.article_uri = candidates.article_uri
                              AND a.matcher_version = :matcher)
         ORDER BY article_uri
         LIMIT :lim
    """), {'lim': article_limit,
           'matcher': entity_content.MATCHER_VERSION}).fetchall()

    for (article_uri,) in unlinked:
        summary['articles'] += 1
        outcome = link_content(conn, article_uri,
                               context={'collection_run_id': run_id})
        summary['links'] += outcome['links']
        summary['mentions'] += outcome['mentions']
        # Record the examination, matched or not. Keyed by matcher version so
        # widening the query terms re-examines the corpus deliberately rather
        # than the backlog being sealed forever.
        conn.execute(text("""
            INSERT INTO bw_entity_link_attempts
                (article_uri, matcher_version, links_found)
            VALUES (:u, :matcher, :found)
            ON CONFLICT (article_uri, matcher_version) DO UPDATE
               SET examined_at = NOW(), links_found = EXCLUDED.links_found
        """), {'u': article_uri, 'matcher': entity_content.MATCHER_VERSION,
               'found': outcome['links']})

    for brand_id in sorted(touched):
        entity_resolution.resolve_entity(conn, brand_id, trigger='ingest')
        entity_projection.project_entity(conn, brand_id)
        entity_projection.project_all_memberships(conn, brand_id)
        summary['resolved_brands'] += 1
    return summary


def on_run_closed(conn, run_id: int, status: str) -> Optional[Dict[str, Any]]:
    """Called by ``market_collect.close_run`` once the ledger row is written.

    Returns None when the entity layer is switched off, so the master flag
    genuinely stops new processing rather than only changing what is read.

    Never raises. The provider data is already durable at this point and a
    fault in processing must not fail the run that collected it — the backlog
    markers mean anything skipped here is retried on the next close.
    """
    from app.services import entity_flags

    # Advance the vendor policies this run asked the provider for, whatever
    # the entity layer is doing. A batch that succeeded with zero records
    # still means those vendors were processed; leaving them due would put the
    # same batch up again on the next pass forever. This is scheduling state,
    # not entity state, so it is not behind the entity flag.
    _advance_requested_policies(conn, run_id, status)

    if not entity_flags.enabled():
        return None
    if status not in ('succeeded', 'partial'):
        # A failed run wrote nothing worth processing. Its snapshots, if any,
        # stay pending and are picked up by the next successful close.
        return None
    # A SAVEPOINT, not just a try/except. Most callers ingest records, call
    # close_run(), and commit afterwards. A *database* error inside this hook
    # aborts the whole transaction, and catching the Python exception does not
    # un-abort it — the caller's commit then fails and PostgreSQL rolls back
    # the provider rows that were supposed to be durable. Rolling back to the
    # savepoint discards only this hook's work and leaves the transaction
    # usable, which is the difference between losing a processing pass and
    # losing the collection that paid for it.
    savepoint = conn.begin_nested()
    try:
        result = process_pending(conn, run_id=run_id)
        savepoint.commit()
    except Exception:                                       # noqa: BLE001
        savepoint.rollback()
        logger.exception('entity post-ingest failed run_id=%s; the provider '
                         'rows are intact and the work stays queued', run_id)
        return None

    # Say so on the run. A run that normalized nothing because every payload
    # was malformed is not a clean success, and the ledger is where an
    # operator looks.
    #
    # Its own savepoint, for the same reason the processing has one. This is a
    # database statement like any other: if it fails, the transaction aborts,
    # and catching the Python exception without rolling back to a savepoint
    # leaves the caller's commit to fail and take the provider rows with it.
    # Protecting the expensive work and then leaving the cheap bookkeeping
    # unprotected would have reintroduced the same defect one statement later.
    metrics_point = conn.begin_nested()
    try:
        status_now = 'partial' if result.get('failed') else None
        conn.execute(text("""
            UPDATE bw_collection_runs
               SET metrics = metrics || CAST(:metrics AS JSONB),
                   status = COALESCE(:status, status)
             WHERE id = :id
        """), {'metrics': _json({'entity': result}), 'status': status_now,
               'id': run_id})
        metrics_point.commit()
    except Exception:                                       # noqa: BLE001
        metrics_point.rollback()
        logger.warning('could not record entity metrics on run_id=%s; the '
                       'processing itself stands', run_id)
    return result


def process_ingest_batch(conn, run_id: Optional[int] = None,
                         snapshot_ids: Optional[Iterable[int]] = None,
                         article_uris: Optional[Iterable[str]] = None,
                         ) -> Dict[str, Any]:
    """Everything that happens after one collection run's writes have landed.

    Returns counts the run ledger can store, including how much failed, so an
    operator can tell "nothing changed" from "nothing ran".
    """
    summary = {'run_id': run_id, 'snapshots': 0, 'normalized': 0,
               'observations': 0, 'failed': 0, 'retried': 0, 'articles': 0,
               'links': 0, 'mentions': 0, 'resolved_brands': 0}
    touched: set = set()

    for snapshot_id in (snapshot_ids or []):
        summary['snapshots'] += 1
        outcome = normalize_snapshot(conn, snapshot_id)
        if outcome['status'] == 'failed':
            summary['failed'] += 1
            continue
        if outcome['status'] in ('normalized', 'partial'):
            summary['normalized'] += 1
            summary['observations'] += outcome.get('written', 0)
            if outcome.get('brand_id'):
                touched.add(int(outcome['brand_id']))

    for article_uri in (article_uris or []):
        summary['articles'] += 1
        outcome = link_content(conn, article_uri,
                               context={'collection_run_id': run_id})
        summary['links'] += outcome['links']
        summary['mentions'] += outcome['mentions']

    # Resolution last, once per entity, rather than once per observation.
    for brand_id in sorted(touched):
        entity_resolution.resolve_entity(conn, brand_id, trigger='ingest')
        summary['resolved_brands'] += 1

    if run_id is not None:
        conn.execute(text("""
            UPDATE bw_collection_runs
               SET records_evaluated = records_evaluated + :evaluated,
                   metrics = metrics || CAST(:metrics AS JSONB)
             WHERE id = :id
        """), {'evaluated': summary['links'] + summary['normalized'],
               'metrics': _json(summary), 'id': run_id})
    return summary


def _json(value: Dict[str, Any]) -> str:
    import json
    return json.dumps(value, default=str)
