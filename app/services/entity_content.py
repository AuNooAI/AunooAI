"""Relating entities to content that already exists, without copying it.

Every article and post stays exactly where it is, in ``articles``, keyed by
uri. What was missing was a way to say *how* a company relates to one — and to
say it more than once for the same article, because a post that names two
vendors relates to both of them and they will not agree about what it says.

Two records come out of that. A **content link** is the relationship: this
company owns this post, or is its subject, or is merely named in it, and it
arrived through this channel. A **mention** is the evaluation of one company in
one piece of content: how relevant, what sentiment, what stance.

Keeping them apart matters because the link is cheap and certain while the
evaluation is expensive and arguable. Linking a vendor's own LinkedIn post to
the vendor needs no model at all — the collector requested that company's page.
Deciding whether a Reddit thread is critical of them does.

The channel is what stops a company's own announcements being counted as other
people's opinions of it. An owned post gets ``stance='owned_claim'`` and never
enters external sentiment, however glowing it is about itself.

Term matching is conservative. A name shorter than four characters, or one that
is an ordinary English word, is stored with ``qualification_required`` and is
never matched on its own — "Command Zero" is safe, "7ai" is not, and a vendor
called "Radiant" would otherwise collect every sunrise on Bluesky.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import text

from app.services.social_sources import classify_source

logger = logging.getLogger(__name__)

MATCHER_VERSION = '1.0'
EXCERPT_LIMIT = 1000

# Terms this short are never matched alone, whatever they are.
MIN_STANDALONE_TERM = 4

# Ordinary words that some company also uses as a name. Matching one of these
# unqualified is how a brand feed fills up with weather reports.
#
# The test is the word, not the vendor. A coined name like "Qevlar" or
# "Intezer" is safe precisely because nobody else writes it; a real word like
# "Radiant" or "Cantina" is not, however distinctive it feels in context. Full
# names are usually multi-word and unaffected — "Radiant Security" is safe
# while the bare alias "Radiant" is not.
_AMBIGUOUS = {
    # general vocabulary
    'radiant', 'method', 'command', 'legion', 'twine', 'embed', 'prophet',
    'variance', 'cantina', 'beacon', 'alpha', 'camelot', 'artemis', 'backline',
    'edge', 'delta', 'zero', 'pre', 'core', 'nexus', 'origin', 'vertex',
    'apex', 'summit', 'anchor', 'compass', 'horizon', 'lighthouse',
    # domain vocabulary, which is worse than general vocabulary here because
    # every post in a security feed contains it
    'security', 'cyber', 'cloud', 'data', 'alert', 'signal', 'sentinel',
    'triage', 'analyst', 'agent', 'copilot', 'shield', 'guard', 'defence',
    'defense', 'threat', 'response', 'detection',
}

# Channels that are the company talking about itself.
OWNED_CHANNELS = frozenset({'owned_web', 'owned_social'})


_URL_RE = re.compile(r'https?://\S+|www\.\S+', re.IGNORECASE)


def normalize_term(term: str) -> str:
    return re.sub(r'\s+', ' ', (term or '').strip().lower())


def strip_urls(blob: str) -> str:
    """Remove links before matching names against prose.

    A company name inside somebody else's URL is not a mention of that
    company. A Bluesky post about 7AI linking to ``whois-secure.com/blog/...``
    matched the vendor Secure.com, because the hyphen reads as a word boundary
    and the domain reads as the name. Links are addresses, not sentences, so
    they come out before the text is searched.
    """
    return _URL_RE.sub(' ', blob or '')


def is_safe_standalone(term: str) -> bool:
    """Whether this term may be matched without further qualification."""
    normalized = normalize_term(term)
    if len(normalized) < MIN_STANDALONE_TERM:
        return False
    if normalized in _AMBIGUOUS:
        return False
    # A single ordinary word is riskier than a phrase; two words is usually
    # enough to be a name rather than a noun.
    if ' ' not in normalized and normalized.rstrip('s') in _AMBIGUOUS:
        return False
    return True


# ---------------------------------------------------------------------------
# Query terms
# ---------------------------------------------------------------------------

def seed_query_terms(conn, brand_id: int) -> Dict[str, int]:
    """Give an entity its own matching vocabulary.

    Separate from ``bw_brands.brand_keywords`` on purpose: the importer rewrote
    that column, which is why a company already claimed by one market could not
    join a second. Terms live here so a market can add vocabulary without
    touching what Brand Watcher already monitors.
    """
    row = conn.execute(text("""
        SELECT display_name, name, brand_keywords, product_keywords,
               people_keywords
          FROM bw_brands WHERE id = :b
    """), {'b': brand_id}).mappings().first()
    if not row:
        return {'written': 0, 'skipped': 0}

    def _list(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except ValueError:
                return []
        return []

    plan: List[tuple] = [(row['display_name'], 'name')]
    for term in _list(row['brand_keywords']):
        plan.append((term, 'alias'))
    for term in _list(row['product_keywords']):
        plan.append((term, 'product'))
    for term in _list(row['people_keywords']):
        plan.append((term, 'person'))

    # The identifier kinds this tenant actually holds are alias, former_name,
    # domain, website_url, linkedin_company_url and crunchbase_url. Only the
    # first two are things a person writes in a sentence; a URL is matched by
    # the link paths, not by scanning prose for it.
    identifiers = conn.execute(text("""
        SELECT kind, display_value, normalized_value
          FROM bw_vendor_identifiers
         WHERE brand_id = :b AND valid_to IS NULL
           AND kind IN ('alias', 'former_name')
    """), {'b': brand_id}).mappings().all()
    for row in identifiers:
        plan.append((row['display_value'] or row['normalized_value'],
                     'alias' if row['kind'] == 'alias' else 'former_name'))

    written = skipped = 0
    seen: Set[tuple] = set()
    for term, kind in plan:
        if not term or not str(term).strip():
            skipped += 1
            continue
        normalized = normalize_term(str(term))
        if (kind, normalized) in seen:
            skipped += 1
            continue
        seen.add((kind, normalized))
        result = conn.execute(text("""
            INSERT INTO bw_entity_query_terms
                (brand_id, term, normalized_term, term_kind,
                 qualification_required, enabled, provenance)
            VALUES (:b, :t, :n, :k, :q, TRUE, CAST(:p AS JSONB))
            ON CONFLICT (brand_id, term_kind, normalized_term)
            WHERE enabled DO NOTHING
            RETURNING id
        """), {'b': brand_id, 't': str(term).strip(), 'n': normalized,
               'k': kind, 'q': not is_safe_standalone(normalized),
               'p': json.dumps({'origin': 'bw_brands', 'field': kind})})
        if result.fetchone():
            written += 1
        else:
            skipped += 1
    return {'written': written, 'skipped': skipped}


def safe_terms_for(conn, brand_ids: Iterable[int]) -> List[Dict[str, Any]]:
    """Terms usable for standalone matching, for the given entities."""
    ids = list(brand_ids)
    if not ids:
        return []
    rows = conn.execute(text("""
        SELECT id, brand_id, term, normalized_term, term_kind
          FROM bw_entity_query_terms
         WHERE brand_id = ANY(:ids) AND enabled
           AND qualification_required = FALSE
         ORDER BY brand_id, length(normalized_term) DESC
    """), {'ids': ids}).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Content links
# ---------------------------------------------------------------------------

def link_content(conn, *, brand_id: int, article_uri: str, relationship: str,
                 channel: str, attribution_method: str,
                 platform: Optional[str] = None,
                 social_account_id: Optional[int] = None,
                 matched_identifier_id: Optional[int] = None,
                 confidence: Optional[float] = None,
                 collection_run_id: Optional[int] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Record how an entity relates to an article. Returns the link id.

    Seeing the same relationship again moves ``last_seen_at`` and nothing else,
    so re-running an ingest does not multiply links, and a brand carrying three
    category rows on one article still has one link.
    """
    row = conn.execute(text("""
        INSERT INTO bw_entity_content_links
            (brand_id, article_uri, relationship, channel, platform,
             social_account_id, attribution_method, matched_identifier_id,
             confidence, collection_run_id, metadata)
        VALUES (:b, :u, :rel, :ch, :plat, :acct, :method, :ident, :conf,
                :run, CAST(:meta AS JSONB))
        ON CONFLICT (brand_id, article_uri, relationship, channel)
        DO UPDATE SET last_seen_at = NOW(),
                      confidence = COALESCE(EXCLUDED.confidence,
                                            bw_entity_content_links.confidence)
        RETURNING id
    """), {'b': brand_id, 'u': article_uri, 'rel': relationship, 'ch': channel,
           'plat': platform, 'acct': social_account_id,
           'method': attribution_method, 'ident': matched_identifier_id,
           'conf': confidence, 'run': collection_run_id,
           'meta': json.dumps(metadata or {})}).fetchone()
    return int(row[0]) if row else None


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------

def dedupe_hash_for(*, mention_type: str, matched_term: Optional[str],
                    channel: str) -> str:
    """Identity of a mention within one (entity, article) pair.

    Deliberately not time-based. The same post found again by the same term is
    the same mention, whenever the collector happened to see it.
    """
    payload = json.dumps({'t': mention_type, 'm': normalize_term(matched_term or ''),
                          'c': channel}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def record_mention(conn, *, brand_id: int, article_uri: str,
                   mention_type: str, channel: str,
                   platform: Optional[str] = None,
                   excerpt: Optional[str] = None,
                   matched_term: Optional[str] = None,
                   matched_query_term_id: Optional[int] = None,
                   content_link_id: Optional[int] = None,
                   relevance: Optional[float] = None,
                   sentiment: Optional[str] = None,
                   stance: Optional[str] = None,
                   status: str = 'pending',
                   evaluation_method: Optional[str] = None,
                   evaluation_model: Optional[str] = None,
                   evaluation_version: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Record one entity's appearance in one article.

    Created ``pending`` by default: found is not the same as judged, and a
    mention with no evaluation must never be counted as neutral sentiment.
    """
    digest = dedupe_hash_for(mention_type=mention_type,
                             matched_term=matched_term, channel=channel)
    row = conn.execute(text("""
        INSERT INTO bw_entity_mentions
            (brand_id, article_uri, content_link_id, mention_type, channel,
             platform, excerpt, matched_query_term_id, relevance, sentiment,
             stance, evaluation_method, evaluation_model, evaluation_version,
             evaluated_at, status, dedupe_hash, metadata)
        VALUES (:b, :u, :link, :mt, :ch, :plat, :ex, :qt, :rel, :sent,
                :stance, :em, :model, :ev,
                CASE WHEN :rel IS NULL THEN NULL ELSE NOW() END,
                :status, :hash, CAST(:meta AS JSONB))
        ON CONFLICT (brand_id, article_uri, dedupe_hash) DO NOTHING
        RETURNING id
    """), {'b': brand_id, 'u': article_uri, 'link': content_link_id,
           'mt': mention_type, 'ch': channel, 'plat': platform,
           'ex': (excerpt or '')[:EXCERPT_LIMIT] or None,
           'qt': matched_query_term_id, 'rel': relevance, 'sent': sentiment,
           'stance': stance, 'em': evaluation_method, 'model': evaluation_model,
           'ev': evaluation_version, 'status': status, 'hash': digest,
           'meta': json.dumps(metadata or {})}).fetchone()
    return int(row[0]) if row else None


def score_mention(conn, mention_id: int, *, relevance: Optional[float],
                  sentiment: Optional[str], stance: Optional[str],
                  method: str, model: Optional[str] = None,
                  version: Optional[str] = None,
                  status: str = 'accepted') -> None:
    """Attach an evaluation to a mention that was already found."""
    conn.execute(text("""
        UPDATE bw_entity_mentions
           SET relevance = :rel, sentiment = :sent, stance = :stance,
               evaluation_method = :m, evaluation_model = :model,
               evaluation_version = :v, evaluated_at = NOW(),
               status = :status, updated_at = NOW()
         WHERE id = :id
    """), {'rel': relevance, 'sent': sentiment, 'stance': stance, 'm': method,
           'model': model, 'v': version, 'status': status, 'id': mention_id})


# ---------------------------------------------------------------------------
# Finding which entities an article is about
# ---------------------------------------------------------------------------

def candidates_from_keywords(conn, article_uri: str) -> List[Dict[str, Any]]:
    """Entities reachable through the keyword monitor's own match records.

    ``keyword_article_matches.keyword_ids`` is a comma-separated text column
    rather than a join table, so the ids are split here. The query is scoped by
    article, and by group at the call sites that sweep a whole group.
    """
    rows = conn.execute(text("""
        SELECT DISTINCT m.brand_id, m.query_term_id, t.term, t.term_kind
          FROM keyword_article_matches kam
          CROSS JOIN LATERAL unnest(string_to_array(kam.keyword_ids, ',')) AS kid
          JOIN bw_keyword_entity_map m
            ON m.monitored_keyword_id = trim(kid)::int
          JOIN bw_entity_query_terms t ON t.id = m.query_term_id
         WHERE kam.article_uri = :u
    """), {'u': article_uri}).mappings().all()
    return [dict(r) for r in rows]


def candidates_from_terms(text_blob: str,
                          terms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Entities named in the text, by whole-word match on safe terms only.

    Word boundaries matter more than they look: without them "7ai" matches
    inside "7aints" and every vendor whose name is a fragment of another word
    collects mentions it has nothing to do with.
    """
    if not text_blob:
        return []
    haystack = strip_urls(text_blob).lower()
    found: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for term in terms:
        normalized = term['normalized_term']
        if normalized not in haystack:
            continue
        if not re.search(rf'(?<!\w){re.escape(normalized)}(?!\w)', haystack):
            continue
        if term['brand_id'] in seen:
            continue
        seen.add(term['brand_id'])
        found.append({'brand_id': term['brand_id'],
                      'query_term_id': term['id'],
                      'term': term['term'],
                      'term_kind': term['term_kind'],
                      'excerpt': _excerpt_around(text_blob, normalized)})
    return found


def _excerpt_around(blob: str, needle: str, window: int = 160) -> str:
    position = blob.lower().find(needle)
    if position < 0:
        return blob[:window]
    start = max(0, position - window // 2)
    return blob[start:start + window].strip()[:EXCERPT_LIMIT]


def channel_for_article(row: Dict[str, Any]) -> tuple:
    """(platform, channel) for an article row with news_source and bias_source."""
    return classify_source(row.get('news_source'), row.get('bias_source'))
