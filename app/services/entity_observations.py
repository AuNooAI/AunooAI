"""Turning provider payloads into dated, attributable field assertions.

A snapshot is a provider's whole answer in the provider's own words. An
observation is one field of that answer, normalized, dated, and attributed. The
gap between the two is where most of the work lives, because the sources do not
agree on vocabulary even when they agree on facts.

Country is the clearest case. The workbook and Crunchbase both say "United
States"; LinkedIn says ``US``, and for a company with offices in two places it
says ``US,IL``. Compared raw, those look like three different answers to the
same question, and an exact-match conflict rule would fire on every vendor. So
codes are mapped to names, and a multi-valued LinkedIn country produces no
observation at all — "the company has offices in the US and Israel" is not an
answer to "where is the headquarters", and guessing the first code would be
wrong for roughly half the vendors that have one.

Two mappings are deliberately absent. Crunchbase's ``employee_band`` is a range
like ``11-50`` and is not a headcount, so it never becomes one. Crunchbase
carries no funding total in this dataset, so it never answers
``funding_total_musd``; the registry enforces that, and this module does not
try to route around it.

Idempotency comes from the snapshot, not from a timestamp. ``store_snapshot``
already refuses a provider record it has seen before, so an unchanged LinkedIn
profile creates no new snapshot, and keying observations to the snapshot id
means re-running normalization over the same rows changes nothing while a
genuinely new reading still becomes a new dated point on the series.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.entity_field_registry import (
    ENTITY_FIELD_POLICY_VERSION, SCOPE_MARKET, coerce, policy, typed_columns,
)

logger = logging.getLogger(__name__)

NORMALIZER_VERSION = '1.0'

# Only the codes that actually appear in collected data, plus the obvious
# neighbours. An unmapped code produces no observation rather than a guess.
_ISO2_COUNTRY = {
    'US': 'United States', 'GB': 'United Kingdom', 'UK': 'United Kingdom',
    'IL': 'Israel', 'FR': 'France', 'DE': 'Germany', 'NL': 'Netherlands',
    'CA': 'Canada', 'AU': 'Australia', 'IN': 'India', 'IT': 'Italy',
    'ES': 'Spain', 'RO': 'Romania', 'TR': 'Turkey', 'SA': 'Saudi Arabia',
    'AE': 'United Arab Emirates', 'BH': 'Bahrain', 'IE': 'Ireland',
    'SG': 'Singapore', 'JP': 'Japan', 'SE': 'Sweden', 'CH': 'Switzerland',
    'BE': 'Belgium', 'DK': 'Denmark', 'FI': 'Finland', 'NO': 'Norway',
    'PL': 'Poland', 'PT': 'Portugal', 'CZ': 'Czechia', 'AT': 'Austria',
}

# Shapes that describe activity rather than company facts. They are skipped
# here on purpose and picked up by the event extractors instead.
_ACTIVITY_SHAPES = {
    ('linkedin_jobs', 'job_posting'),
    ('vendor_web', 'page_state'),
}


class NormalizationError(Exception):
    """Raised when a payload cannot be mapped. Never swallowed silently."""


# ---------------------------------------------------------------------------
# Identity and hashing
# ---------------------------------------------------------------------------

def mint_source_record_id(kind: str, *, market_id: Optional[int] = None,
                          **parts: Any) -> str:
    """A stable id for the provider record an observation came from.

    Market-scoped fields carry the market inside the id. The unique index on
    observations does not include ``market_id``, so without this two markets
    asserting the same value from one source record would collide and the
    second would be silently dropped.
    """
    tail = ':'.join(f"{k}={v}" for k, v in sorted(parts.items()) if v is not None)
    base = f"{kind}:{tail}" if tail else kind
    if market_id is not None:
        return f"{base}:market={market_id}"
    return base


def content_hash_for(field_key: str, value: Any, source: str,
                     unit: Optional[str] = None) -> str:
    """Hash the assertion, not the row.

    Two readings of the same value from the same source record are the same
    assertion, so re-normalizing is a no-op. A changed value hashes
    differently and becomes a new dated observation.
    """
    payload = json.dumps(
        {'f': field_key, 'v': value, 's': source, 'u': unit},
        sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _canonical_country(raw: Any) -> Optional[str]:
    """A country name, or None when the source did not give exactly one.

    ``US,IL`` means the company has people in two countries. It does not say
    which one holds the headquarters, so it answers nothing.
    """
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if ',' in value:
        return None
    if len(value) <= 3 and value.isalpha():
        return _ISO2_COUNTRY.get(value.upper())
    return value


def _as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Writing observations
# ---------------------------------------------------------------------------

def record_observation(conn, *, brand_id: int, field_key: str, value: Any,
                       source: str, source_record_id: str,
                       observed_at: datetime,
                       market_id: Optional[int] = None,
                       source_url: Optional[str] = None,
                       snapshot_id: Optional[int] = None,
                       article_uri: Optional[str] = None,
                       collection_run_id: Optional[int] = None,
                       effective_at: Optional[datetime] = None,
                       confidence: Optional[float] = None,
                       authority: Optional[int] = None,
                       metadata: Optional[Dict[str, Any]] = None,
                       ) -> Optional[int]:
    """Insert one observation. Returns its id, or None if it already existed.

    A value that does not survive ``coerce`` is not an observation. That covers
    nulls, empty strings, and the zeroes that stand in for missing headcounts,
    and returning None here is the normal outcome rather than an error.
    """
    p = policy(field_key)
    if not p.accepts(source):
        raise NormalizationError(
            f"source {source!r} may not answer {field_key!r}")

    coerced = coerce(field_key, value)
    if coerced is None:
        return None

    if (p.scope == SCOPE_MARKET) != (market_id is not None):
        raise NormalizationError(
            f"{field_key!r} is {p.scope}-scoped; market_id="
            f"{market_id!r} does not match")

    value_text, value_number, value_date, unit = typed_columns(field_key, coerced)
    digest = content_hash_for(field_key, coerced, source, unit)

    row = conn.execute(text("""
        INSERT INTO bw_entity_observations
            (brand_id, market_id, field_key, value_json, value_text,
             value_number, value_date, unit, source, source_record_id,
             source_url, snapshot_id, article_uri, collection_run_id,
             observed_at, effective_at, confidence, authority, status,
             normalizer_version, content_hash, metadata)
        VALUES
            (:brand_id, :market_id, :field_key, CAST(:value_json AS JSONB),
             :value_text, :value_number, CAST(:value_date AS DATE), :unit,
             :source, :source_record_id, :source_url, :snapshot_id,
             :article_uri, :collection_run_id, :observed_at, :effective_at,
             :confidence, :authority, 'active', :normalizer_version,
             :content_hash, CAST(:metadata AS JSONB))
        ON CONFLICT (brand_id, field_key, source, source_record_id, content_hash)
        DO NOTHING
        RETURNING id
    """), {
        'brand_id': brand_id, 'market_id': market_id, 'field_key': field_key,
        'value_json': json.dumps(coerced), 'value_text': value_text,
        'value_number': value_number, 'value_date': value_date, 'unit': unit,
        'source': source, 'source_record_id': source_record_id,
        'source_url': source_url, 'snapshot_id': snapshot_id,
        'article_uri': article_uri, 'collection_run_id': collection_run_id,
        'observed_at': _as_utc(observed_at), 'effective_at': effective_at,
        'confidence': confidence,
        'authority': authority if authority is not None else p.authority_of(source),
        'normalizer_version': NORMALIZER_VERSION,
        'content_hash': digest,
        'metadata': json.dumps(metadata or {}),
    }).fetchone()
    return int(row[0]) if row else None


# ---------------------------------------------------------------------------
# Per-shape mappers, written against the payloads actually collected
# ---------------------------------------------------------------------------

def _map_linkedin_profile(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """LinkedIn company profile -> headcount, followers, country, industry.

    ``founded`` is a year, ``employee_count`` a number, ``followers`` a number,
    and ``description`` is the company's own words, which is why the registry
    treats it as self-reported. ``headquarters`` is a city string and is kept
    as metadata rather than parsed into a country.
    """
    out: List[Dict[str, Any]] = [
        {'field_key': 'employee_count', 'value': data.get('employee_count')},
        {'field_key': 'followers_linkedin', 'value': data.get('followers')},
        {'field_key': 'founded_year', 'value': data.get('founded')},
        {'field_key': 'industry', 'value': data.get('industry')},
        {'field_key': 'description', 'value': data.get('description')},
    ]
    country = _canonical_country(data.get('country'))
    if country:
        out.append({'field_key': 'hq_country', 'value': country,
                    'metadata': {'headquarters': data.get('headquarters')}})
    return out


def _map_crunchbase(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Crunchbase organization -> status, round type, country, description.

    Two fields are pointedly not mapped. ``employee_band`` is a range such as
    ``11-50`` and is not a headcount. There is no total funding amount in this
    dataset at all, so nothing here can answer ``funding_total_musd`` — the
    registry refuses the source outright, and that is the only reason a vendor
    page has never shown an invented dollar figure.
    """
    operating = data.get('operating_status')
    if data.get('acquired_by'):
        operating = 'acquired'
    out: List[Dict[str, Any]] = [
        {'field_key': 'operating_status', 'value': operating,
         'metadata': {'ipo_status': data.get('ipo_status'),
                      'acquired_by': data.get('acquired_by')}},
        {'field_key': 'last_funding_type', 'value': data.get('last_funding_type'),
         'metadata': {'num_funding_rounds': data.get('num_funding_rounds'),
                      'investors': data.get('investors'),
                      'lead_investors': data.get('lead_investors')}},
        {'field_key': 'description', 'value': data.get('about')},
    ]
    country = _canonical_country(data.get('country'))
    if country:
        out.append({'field_key': 'hq_country', 'value': country,
                    'metadata': {'address': data.get('address')}})
    return out


def _map_workbook_metric(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The imported workbook row -> headcount and funding status.

    ``metrics.employee_count`` is zero for many rows, which is the shape of a
    blank cell rather than a company with no staff. ``coerce`` drops it, so
    those rows produce no headcount observation and the field stays unknown
    instead of becoming a confident zero.
    """
    metrics = data.get('metrics') or {}
    return [
        {'field_key': 'employee_count', 'value': metrics.get('employee_count'),
         'metadata': {'employee_growth_ytd': metrics.get('employee_growth_ytd'),
                      'growth_has_baseline': data.get('growth_has_baseline')}},
        {'field_key': 'funding_status', 'value': data.get('funding_status')},
    ]


_MAPPERS = {
    ('linkedin_company_profile', 'profile'): _map_linkedin_profile,
    ('crunchbase_company', 'funding'): _map_crunchbase,
    ('workbook', 'metric'): _map_workbook_metric,
}


# ---------------------------------------------------------------------------
# Snapshot normalization
# ---------------------------------------------------------------------------

def normalize_snapshot(conn, snapshot_id: int) -> Dict[str, Any]:
    """Normalize one snapshot into observations.

    A shape with no mapper is marked ``skipped`` with a reason, never guessed
    at from field names. A mapper that raises marks the snapshot ``failed`` and
    leaves it for retry; the snapshot itself is already durable and is not
    rolled back.
    """
    row = conn.execute(text("""
        SELECT id, brand_id, market_id, source, snapshot_type, data,
               observed_at, collection_run_id
        FROM bw_vendor_snapshots WHERE id = :id
    """), {'id': snapshot_id}).mappings().first()
    if not row:
        raise NormalizationError(f"snapshot {snapshot_id} not found")

    shape = (row['source'], row['snapshot_type'])
    result = {'snapshot_id': snapshot_id, 'brand_id': row['brand_id'],
              'shape': '/'.join(shape), 'written': 0, 'unchanged': 0,
              'fields': [], 'status': 'normalized', 'reason': None}

    if shape in _ACTIVITY_SHAPES:
        _set_status(conn, snapshot_id, 'skipped', None)
        result.update(status='skipped',
                      reason='activity shape; handled by event extraction')
        return result

    mapper = _MAPPERS.get(shape)
    if mapper is None:
        _set_status(conn, snapshot_id, 'skipped', f"no mapper for {shape[0]}/{shape[1]}")
        result.update(status='skipped', reason=f"no mapper for {shape[0]}/{shape[1]}")
        return result

    data = row['data']
    if isinstance(data, str):
        data = json.loads(data)

    try:
        assertions = mapper(data or {})
    except Exception as exc:                       # noqa: BLE001 - recorded, not hidden
        _set_status(conn, snapshot_id, 'failed', str(exc)[:500])
        result.update(status='failed', reason=str(exc))
        return result

    partial = False
    for item in assertions:
        field_key = item['field_key']
        try:
            obs_id = record_observation(
                conn, brand_id=row['brand_id'], field_key=field_key,
                value=item.get('value'), source=row['source'],
                source_record_id=mint_source_record_id(
                    'snapshot', id=snapshot_id,
                    market_id=None if policy(field_key).scope != SCOPE_MARKET
                    else row['market_id']),
                observed_at=row['observed_at'],
                market_id=(row['market_id']
                           if policy(field_key).scope == SCOPE_MARKET else None),
                snapshot_id=snapshot_id,
                collection_run_id=row['collection_run_id'],
                metadata=item.get('metadata'),
            )
        except NormalizationError as exc:
            logger.warning("snapshot_id=%s field=%s not mapped: %s",
                           snapshot_id, field_key, exc)
            partial = True
            continue
        if obs_id:
            result['written'] += 1
            result['fields'].append(field_key)
        else:
            result['unchanged'] += 1

    status = 'partial' if partial else 'normalized'
    _set_status(conn, snapshot_id, status, None)
    result['status'] = status
    return result


def _set_status(conn, snapshot_id: int, status: str, error: Optional[str]) -> None:
    conn.execute(text("""
        UPDATE bw_vendor_snapshots
           SET normalization_status = :s,
               normalization_error = :e,
               schema_version = COALESCE(schema_version, :v)
         WHERE id = :id
    """), {'s': status, 'e': error, 'v': NORMALIZER_VERSION, 'id': snapshot_id})


def pending_snapshot_ids(conn, limit: int = 500,
                         after_id: int = 0) -> List[int]:
    """Snapshots waiting to be normalized, oldest first, keyed for resume."""
    rows = conn.execute(text("""
        SELECT id FROM bw_vendor_snapshots
         WHERE normalization_status IN ('pending', 'failed')
           AND id > :after
         ORDER BY id
         LIMIT :limit
    """), {'after': after_id, 'limit': limit}).fetchall()
    return [int(r[0]) for r in rows]


def policy_version() -> str:
    return ENTITY_FIELD_POLICY_VERSION
