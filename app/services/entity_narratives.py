"""Generated prose that can be checked against what we actually know.

The failure this is built against is the plausible paragraph: a summary that
reads well, contains a number nobody collected, and cannot be traced back to
anything. It is the most damaging output the system can produce, because it is
the one a reader is least able to doubt.

Three mechanics make that checkable.

A **facts pack** is assembled deterministically before any model runs. It
carries canonical values with their observation ids and dates, events with
their corroboration, mention counts by channel, and — importantly — what is
missing: fields with no source, channels with no coverage, conflicts still
open. The model writes from this and nothing else.

**Evidence rows** record what the narrative is allowed to cite. Prose that
names an event or a post that is not in ``bw_narrative_evidence`` is a lint
failure, not a stylistic preference.

**Lint** re-reads the finished text and pulls out every number in it. Any
figure that does not appear in the facts pack is reported. This catches the
specific way these summaries go wrong: not invented sentences, which are rare,
but invented precision — a headcount rounded into a different number, a count
of posts nobody counted.

Empty is not the same as quiet. A channel with no coverage is stated as "we
are not collecting this", never as "nothing was said", because the second is a
claim about the world made from an absence in our own pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

GENERATOR_VERSION = '1.0'
PROMPT_VERSION = '1.0'

NARRATIVE_TYPES = ('brand_brief', 'theme_cluster', 'social_narrative',
                   'event_summary')

# Numbers that carry no claim: years, small ordinals in phrases like "one of".
_NUMBER = re.compile(r'(?<![\w.])(\d[\d,]*\.?\d*)(?![\w])')
_HARMLESS = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10'}


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

def build_facts(conn, brand_id: int, *, days: int = 90) -> Dict[str, Any]:
    """Everything the prose is allowed to assert, assembled without a model."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    brand = conn.execute(text("""
        SELECT id, display_name FROM bw_brands WHERE id = :b
    """), {'b': brand_id}).mappings().first()
    if not brand:
        raise ValueError(f'no such brand: {brand_id}')

    fields = [dict(r) for r in conn.execute(text("""
        SELECT c.field_key, c.value_text, c.value_number, c.unit, c.status,
               c.resolution_reason, c.observation_id, o.source, o.observed_at
          FROM bw_entity_canonical_fields c
          JOIN bw_entity_observations o ON o.id = c.observation_id
         WHERE c.brand_id = :b AND c.market_id IS NULL
         ORDER BY c.field_key
    """), {'b': brand_id}).mappings().all()]

    events = [dict(r) for r in conn.execute(text("""
        SELECT e.id, e.event_type, e.title, e.occurred_at, e.date_precision,
               e.corroboration, e.status,
               (SELECT count(DISTINCT independence_key)
                  FROM bw_entity_event_evidence v
                 WHERE v.event_id = e.id
                   AND v.relationship IN ('supports','originates')) AS sources
          FROM bw_entity_events e
          JOIN bw_entity_event_entities ee ON ee.event_id = e.id
         WHERE ee.brand_id = :b AND e.status = 'active'
           AND COALESCE(e.occurred_at, e.first_observed_at) >= :cutoff
         ORDER BY COALESCE(e.occurred_at, e.first_observed_at) DESC
         LIMIT 40
    """), {'b': brand_id, 'cutoff': cutoff}).mappings().all()]

    mentions = [dict(r) for r in conn.execute(text("""
        SELECT channel, platform, status,
               count(*) AS total,
               count(*) FILTER (WHERE sentiment IS NOT NULL) AS evaluated,
               count(*) FILTER (WHERE sentiment ILIKE 'positive') AS positive,
               count(*) FILTER (WHERE sentiment ILIKE 'negative') AS negative
          FROM bw_entity_mentions
         WHERE brand_id = :b
         GROUP BY 1, 2, 3 ORDER BY 4 DESC
    """), {'b': brand_id}).mappings().all()]

    # What we do not know is part of the brief. A field with no source and a
    # channel with no coverage are both reportable, and both are routinely
    # written up as if they were findings about the company.
    missing_fields = [dict(r) for r in conn.execute(text("""
        SELECT k.field_key
          FROM (SELECT unnest(CAST(:fields AS text[])) AS field_key) k
         WHERE NOT EXISTS (SELECT 1 FROM bw_entity_canonical_fields c
                            WHERE c.brand_id = :b AND c.market_id IS NULL
                              AND c.field_key = k.field_key)
    """), {'b': brand_id,
           'fields': ['employee_count', 'funding_total_musd', 'hq_country',
                      'founded_year', 'operating_status']}).mappings().all()]

    conflicts = [dict(r) for r in conn.execute(text("""
        SELECT field_key, status, resolution_reason
          FROM bw_entity_canonical_fields
         WHERE brand_id = :b AND status IN ('conflict', 'stale')
    """), {'b': brand_id}).mappings().all()]

    owned = sum(m['total'] for m in mentions
                if m['channel'] in ('owned_web', 'owned_social'))
    external = sum(m['total'] for m in mentions
                   if m['channel'] not in ('owned_web', 'owned_social'))
    unevaluated = sum(m['total'] for m in mentions if m['status'] == 'pending')

    return {
        'brand_id': brand_id,
        'display_name': brand['display_name'],
        'window_days': days,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'canonical_fields': fields,
        'missing_fields': [m['field_key'] for m in missing_fields],
        'conflicts': conflicts,
        'events': events,
        'event_count': len(events),
        'mentions_by_channel': mentions,
        'owned_content_count': owned,
        'external_mention_count': external,
        'unevaluated_mention_count': unevaluated,
        # Stated explicitly so prose cannot read silence as absence of comment.
        'coverage_caveats': _caveats(mentions, external, unevaluated),
    }


def _caveats(mentions: List[Dict[str, Any]], external: int,
             unevaluated: int) -> List[str]:
    out: List[str] = []
    if external == 0:
        out.append('No external mentions have been collected for this company. '
                   'That is a gap in collection, not evidence that nobody '
                   'discussed it.')
    if unevaluated:
        out.append(f'{unevaluated} mention(s) are found but not yet evaluated, '
                   f'so they carry no sentiment and are excluded from any '
                   f'sentiment figure.')
    platforms = {m['platform'] for m in mentions if m['platform']}
    if not platforms:
        out.append('No social platform coverage is configured for this company.')
    return out


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

def lint(narrative: str, facts: Dict[str, Any],
         evidence_ids: Optional[Dict[str, List[int]]] = None) -> List[Dict[str, Any]]:
    """Report claims the facts pack does not support.

    The check is on numbers because that is where these summaries actually go
    wrong. A sentence with no figures is hard to falsify and rarely dangerous;
    "headcount grew to 145" is checkable, and if 145 is not in the pack it was
    invented or mistranscribed.
    """
    problems: List[Dict[str, Any]] = []
    known = _known_numbers(facts)

    for match in _NUMBER.finditer(narrative or ''):
        raw = match.group(1)
        cleaned = raw.replace(',', '').rstrip('.')
        if cleaned in _HARMLESS:
            continue
        if _is_year(cleaned) and cleaned in known:
            continue
        if cleaned not in known:
            problems.append({
                'kind': 'unsupported_number',
                'value': raw,
                'context': narrative[max(0, match.start() - 60):match.end() + 60],
                'detail': 'this figure does not appear in the facts pack',
            })

    if evidence_ids is not None:
        cited = set(evidence_ids.get('events') or [])
        available = {e['id'] for e in facts.get('events', [])}
        for event_id in cited - available:
            problems.append({'kind': 'uncited_event', 'value': event_id,
                             'detail': 'cited event is not in the facts pack'})

    # Reading our own empty pipeline as the market having nothing to say.
    # This fires only when the prose actually makes a silence claim — a brief
    # that simply does not discuss coverage is not asserting anything about
    # it, and flagging that would make the check noise people learn to ignore.
    if facts.get('external_mention_count') == 0 and narrative:
        claims_silence = re.search(
            r'\b(nobody|no one|no-one|little attention|no mentions?|'
            r'no discussion|unnoticed|silence|nothing was said)\b',
            narrative, re.IGNORECASE)
        explains_gap = re.search(
            r'not collect|no coverage|not configured|gap|not monitor',
            narrative, re.IGNORECASE)
        if claims_silence and not explains_gap:
            problems.append({
                'kind': 'silence_read_as_absence',
                'context': narrative[max(0, claims_silence.start() - 60):
                                     claims_silence.end() + 60],
                'detail': ('the text reports silence, but no external mentions '
                           'have been collected — that is a gap in collection, '
                           'not evidence that nobody spoke'),
            })
    return problems


def _known_numbers(facts: Dict[str, Any]) -> set:
    """Every number the facts pack contains, in the forms prose would use."""
    known: set = set()

    def _add(value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            text_value = f'{value:g}'
            known.add(text_value)
            if float(value).is_integer():
                known.add(str(int(value)))
            return
        if isinstance(value, str):
            for match in _NUMBER.finditer(value):
                known.add(match.group(1).replace(',', ''))

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for item in node.values():
                _walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)
        else:
            _add(node)

    _walk(facts)
    # Counts the prose may legitimately state.
    for key in ('event_count', 'owned_content_count', 'external_mention_count',
                'unevaluated_mention_count', 'window_days'):
        _add(facts.get(key))
    return known


def _is_year(value: str) -> bool:
    return len(value) == 4 and value.isdigit() and 1800 < int(value) < 2200


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_narrative(conn, *, brand_id: int, narrative: str,
                   facts: Dict[str, Any], narrative_type: str = 'brand_brief',
                   model_used: Optional[str] = None,
                   evidence: Optional[List[Dict[str, Any]]] = None,
                   status: str = 'draft') -> Dict[str, Any]:
    """Store a draft, supersede its predecessor, and record what it cites.

    A regenerated brief points at the one it replaces rather than overwriting
    it, so a reader can see what changed and when the assessment moved.
    """
    if narrative_type not in NARRATIVE_TYPES:
        raise ValueError(f'unknown narrative type {narrative_type!r}')

    problems = lint(narrative, facts)

    previous = conn.execute(text("""
        SELECT id FROM bw_tracker_narratives
         WHERE brand_id = :b AND narrative_type = :t
           AND status IN ('draft', 'approved')
         ORDER BY generated_at DESC LIMIT 1
    """), {'b': brand_id, 't': narrative_type}).scalar()

    row = conn.execute(text("""
        INSERT INTO bw_tracker_narratives
            (brand_id, narrative, data_summary, days_back, narrative_type,
             status, facts, model_used, prompt_version, generator_version,
             source_cutoff_at, supersedes_id, lint)
        VALUES (:b, :narrative, CAST(:summary AS JSONB), :days, :type, :status,
                CAST(:facts AS JSONB), :model, :prompt_v, :gen_v, NOW(),
                :supersedes, CAST(:lint AS JSONB))
        RETURNING id
    """), {'b': brand_id, 'narrative': narrative,
           'summary': json.dumps({'event_count': facts.get('event_count'),
                                  'external_mentions':
                                      facts.get('external_mention_count')}),
           'days': facts.get('window_days'), 'type': narrative_type,
           'status': status, 'facts': json.dumps(facts, default=str),
           'model': model_used, 'prompt_v': PROMPT_VERSION,
           'gen_v': GENERATOR_VERSION, 'supersedes': previous,
           'lint': json.dumps(problems)}).fetchone()
    narrative_id = int(row[0])

    if previous:
        conn.execute(text("""
            UPDATE bw_tracker_narratives SET status = 'superseded'
             WHERE id = :id
        """), {'id': previous})

    for rank, item in enumerate(evidence or []):
        conn.execute(text("""
            INSERT INTO bw_narrative_evidence
                (narrative_id, evidence_type, article_uri, event_id,
                 mention_id, observation_id, snapshot_id, relationship, rank,
                 excerpt)
            VALUES (:n, :t, :uri, :event, :mention, :obs, :snap, :rel, :rank,
                    :ex)
        """), {'n': narrative_id, 't': item['evidence_type'],
               'uri': item.get('article_uri'), 'event': item.get('event_id'),
               'mention': item.get('mention_id'),
               'obs': item.get('observation_id'),
               'snap': item.get('snapshot_id'),
               'rel': item.get('relationship', 'supports'), 'rank': rank,
               'ex': (item.get('excerpt') or '')[:1000] or None})

    return {'narrative_id': narrative_id, 'supersedes_id': previous,
            'lint': problems, 'clean': not problems}


def evidence_from_facts(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The rows a brief written from this pack is entitled to cite."""
    evidence: List[Dict[str, Any]] = []
    for event in facts.get('events', []):
        evidence.append({'evidence_type': 'event', 'event_id': event['id'],
                         'excerpt': event['title']})
    for field in facts.get('canonical_fields', []):
        evidence.append({'evidence_type': 'observation',
                         'observation_id': field['observation_id'],
                         'excerpt': f"{field['field_key']}="
                                    f"{field['value_text'] or field['value_number']}"})
    return evidence


def narratives_for(conn, brand_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT n.id, n.narrative_type, n.status, n.generated_at, n.model_used,
               n.generator_version, n.supersedes_id,
               jsonb_array_length(n.lint) AS lint_problems,
               (SELECT count(*) FROM bw_narrative_evidence e
                 WHERE e.narrative_id = n.id) AS evidence_count
          FROM bw_tracker_narratives n
         WHERE n.brand_id = :b
         ORDER BY n.generated_at DESC LIMIT :lim
    """), {'b': brand_id, 'lim': limit}).mappings().all()
    return [dict(r) for r in rows]
