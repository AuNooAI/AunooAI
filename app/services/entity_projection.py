"""Copying the winning values into the shapes that lists and filters read.

``bw_entity_profiles`` is a cache. Every value in it is already in
``bw_entity_canonical_fields``, and the only reason it exists is that filtering
eighty vendors by headcount and country should not mean joining a tall
key-value table once per column. The same goes for the typed ``category`` and
``sub_category`` columns on ``bw_market_brands``.

Being a cache has one consequence worth stating plainly: nothing may write here
except this module, and this module writes only what resolution has already
decided. If the projection and the canonical rows ever disagree, the canonical
rows are right and the projection is stale.

A field in conflict still projects. Hiding a disputed value would leave a
vendor page emptier than the evidence warrants; the status travels with it so
the page can mark it rather than omit it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.services.entity_field_registry import REGISTRY, SCOPE_ENTITY

logger = logging.getLogger(__name__)

# profile column -> field key, for the columns the registry projects.
_PROFILE_COLUMNS = {
    p.profile_column: key for key, p in REGISTRY.items()
    if p.scope == SCOPE_ENTITY and p.profile_column
}

_INTEGER_COLUMNS = {'founded_year', 'employee_count', 'followers_linkedin'}
_NUMERIC_COLUMNS = {'funding_total_musd'}


def project_entity(conn, brand_id: int) -> Dict[str, Any]:
    """Rebuild one entity's profile row from its canonical fields."""
    rows = conn.execute(text("""
        SELECT c.field_key, c.value_json, c.value_text, c.value_number,
               c.status, o.source, o.observed_at
          FROM bw_entity_canonical_fields c
          JOIN bw_entity_observations o ON o.id = c.observation_id
         WHERE c.brand_id = :brand_id AND c.market_id IS NULL
    """), {'brand_id': brand_id}).mappings().all()

    by_field = {r['field_key']: r for r in rows}
    values: Dict[str, Any] = {'brand_id': brand_id}

    for column, field_key in _PROFILE_COLUMNS.items():
        row = by_field.get(field_key)
        if row is None:
            values[column] = None
            continue
        if column in _INTEGER_COLUMNS:
            values[column] = (int(row['value_number'])
                              if row['value_number'] is not None else None)
        elif column in _NUMERIC_COLUMNS:
            values[column] = row['value_number']
        else:
            values[column] = row['value_text']

    # Headcount carries its own provenance in the projection, because a list
    # showing "310 people" without saying who counted them and when is the
    # thing this whole change exists to stop.
    headcount = by_field.get('employee_count')
    values['employee_count_source'] = headcount['source'] if headcount else None
    values['employee_count_observed_at'] = (headcount['observed_at']
                                            if headcount else None)

    columns = [c for c in values if c != 'brand_id']
    assignments = ', '.join(f"{c} = EXCLUDED.{c}" for c in columns)
    conn.execute(text(f"""
        INSERT INTO bw_entity_profiles (brand_id, {', '.join(columns)},
                                        canonical_updated_at)
        VALUES (:brand_id, {', '.join(':' + c for c in columns)}, NOW())
        ON CONFLICT (brand_id) DO UPDATE
           SET {assignments}, canonical_updated_at = NOW()
    """), values)
    return values


def project_membership(conn, brand_id: int, market_id: int) -> Dict[str, Any]:
    """Copy market-scoped canonical values onto the membership row.

    Taxonomy is analyst-controlled, so in practice this projects a value the
    import or an operator set. It still goes through resolution rather than
    being written directly, so the observation that decided it is recorded.
    """
    rows = conn.execute(text("""
        SELECT field_key, value_text, observation_id
          FROM bw_entity_canonical_fields
         WHERE brand_id = :brand_id AND market_id = :market_id
    """), {'brand_id': brand_id, 'market_id': market_id}).mappings().all()
    by_field = {r['field_key']: r for r in rows}

    category = by_field.get('market_category')
    sub_category = by_field.get('market_sub_category')
    params = {
        'brand_id': brand_id, 'market_id': market_id,
        'category': category['value_text'] if category else None,
        'category_obs': category['observation_id'] if category else None,
        'sub_category': sub_category['value_text'] if sub_category else None,
        'sub_category_obs': (sub_category['observation_id']
                             if sub_category else None),
    }
    # COALESCE keeps a hand-set taxonomy that has no observation behind it yet,
    # which is the state every membership is in before the backfill runs.
    conn.execute(text("""
        UPDATE bw_market_brands
           SET category = COALESCE(:category, category),
               category_observation_id = COALESCE(:category_obs,
                                                  category_observation_id),
               sub_category = COALESCE(:sub_category, sub_category),
               sub_category_observation_id = COALESCE(:sub_category_obs,
                                                      sub_category_observation_id),
               updated_at = NOW()
         WHERE brand_id = :brand_id AND market_id = :market_id
    """), params)
    return params


def project_all_memberships(conn, brand_id: int) -> int:
    """Project every market this entity belongs to. One reading, many markets."""
    markets = conn.execute(text("""
        SELECT market_id FROM bw_market_brands WHERE brand_id = :brand_id
    """), {'brand_id': brand_id}).fetchall()
    for (market_id,) in markets:
        project_membership(conn, brand_id, int(market_id))
    return len(markets)


def profile_of(conn, brand_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT * FROM bw_entity_profiles WHERE brand_id = :brand_id
    """), {'brand_id': brand_id}).mappings().first()
    return dict(row) if row else None
