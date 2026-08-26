"""Reading the same field two ways, and reporting where they disagree.

The cutover this supports is small but easy to get wrong. Vendor lists and
filters currently read the imported workbook JSON; they should read the
resolved canonical value. Switching that over blind would silently change which
vendors match a headcount filter, and nobody would notice until a customer
asked why a company had vanished from a list.

So the two readings are defined once, here, as paired SQL expressions. The
filter builder picks a side by flag, and the comparison runs both and reports
the difference. Defining them in one place is the point: if the filter and the
comparison drifted apart, the comparison would certify a cutover that does not
match what the filter actually does.

A difference is not automatically a fault. Most are the system working — a
LinkedIn reading displaced a workbook value, which is the entire purpose. What
matters is the shape of the differences: a headcount moving by a few percent is
expected, a country changing is worth a look, and a value that existed before
and is now missing would be a regression, because a filter that used to match a
vendor should not stop matching it just because we started reading a better
source.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services import entity_flags

logger = logging.getLogger(__name__)


class FieldRead:
    """One field, expressed over both the old and the new store.

    ``legacy`` reads ``bw_market_brands.baseline``; ``canonical`` reads the
    resolved projection. Both are SQL fragments over ``mb`` (the membership)
    and ``p`` (``bw_entity_profiles``), so a caller only has to join ``p``.
    """

    def __init__(self, key: str, legacy: str, canonical: str,
                 numeric: bool = False, tolerance: float = 0.0):
        self.key = key
        self.legacy = legacy
        self.canonical = canonical
        self.numeric = numeric
        # Relative movement below this is expected drift rather than a change
        # worth an operator's attention.
        self.tolerance = tolerance

    def expression(self, canonical: Optional[bool] = None) -> str:
        use_canonical = (entity_flags.canonical_read() if canonical is None
                         else canonical)
        return self.canonical if use_canonical else self.legacy


READS: Dict[str, FieldRead] = {
    'funding_status': FieldRead(
        'funding_status',
        legacy="mb.baseline->'funding_baseline'->>'status'",
        canonical='p.funding_status'),
    'hq_country': FieldRead(
        'hq_country',
        legacy="mb.baseline->>'hq_country'",
        canonical='p.hq_country'),
    # Taxonomy is analyst-controlled and market-relative, so its canonical home
    # is the typed membership column rather than the entity profile.
    'category': FieldRead(
        'category',
        legacy="mb.baseline->'taxonomy'->>'category'",
        canonical='mb.category'),
    'sub_category': FieldRead(
        'sub_category',
        legacy="mb.baseline->'taxonomy'->>'sub_category'",
        canonical='mb.sub_category'),
    'employee_count': FieldRead(
        'employee_count',
        # NULLIF so a blank workbook cell stored as 0 is not reported as the
        # legacy side disagreeing with canonical. Canonical never had the
        # zero, so without this every such vendor looked like real drift.
        legacy="NULLIF((mb.baseline->'metrics'->>'employee_count')::numeric, 0)",
        canonical='p.employee_count::numeric',
        numeric=True, tolerance=0.02),
    'founded_year': FieldRead(
        'founded_year',
        legacy="(mb.baseline->>'founded_year')::numeric",
        canonical='p.founded_year::numeric',
        numeric=True),
    'funding_total_musd': FieldRead(
        'funding_total_musd',
        legacy="(mb.baseline->'funding_baseline'->>'total_musd')::numeric",
        canonical='p.funding_total_musd',
        numeric=True, tolerance=0.001),
}

# The join every caller needs to make the canonical side resolvable. A LEFT
# JOIN on purpose: a vendor with no resolved profile yet must still appear,
# reading as unknown rather than dropping out of the list.
PROFILE_JOIN = ('LEFT JOIN bw_entity_profiles p ON p.brand_id = mb.brand_id')


def expression(field: str, canonical: Optional[bool] = None) -> str:
    return READS[field].expression(canonical)


# ---------------------------------------------------------------------------
# Shadow comparison
# ---------------------------------------------------------------------------

def compare_market(conn, market_id: int) -> Dict[str, Any]:
    """Read every vendor both ways and classify the differences.

    Returns per-field counts and the individual rows that differ, so a cutover
    decision rests on what actually changed rather than on a total.
    """
    selects = []
    for field, read in READS.items():
        selects.append(f'{read.legacy} AS legacy_{field}')
        selects.append(f'{read.canonical} AS canonical_{field}')

    rows = conn.execute(text(f"""
        SELECT mb.brand_id, b.display_name, {', '.join(selects)}
          FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
          {PROFILE_JOIN}
         WHERE mb.market_id = :m
         ORDER BY b.display_name
    """), {'m': market_id}).mappings().all()

    summary: Dict[str, Dict[str, Any]] = {
        field: {'compared': 0, 'same': 0, 'changed': 0, 'gained': 0,
                'lost': 0, 'placeholder_dropped': 0, 'within_tolerance': 0,
                'examples': []}
        for field in READS
    }

    for row in rows:
        for field, read in READS.items():
            legacy = row[f'legacy_{field}']
            canonical = row[f'canonical_{field}']
            bucket = summary[field]
            bucket['compared'] += 1

            if legacy is None and canonical is None:
                bucket['same'] += 1
            elif legacy is None:
                # We now know something we did not before. Never a regression.
                bucket['gained'] += 1
            elif canonical is None:
                if _is_placeholder_zero(field, legacy):
                    # A blank workbook cell that the old read served as 0.
                    # Losing it is the fix, not a regression: a headcount of
                    # zero is not a company, and a "fewer than 10 staff"
                    # filter should never have matched on it.
                    bucket['placeholder_dropped'] += 1
                    _example(bucket, row, legacy, canonical,
                             'placeholder_dropped')
                else:
                    # A real value that would become unknown. This is the only
                    # class that can silently shrink a customer's list.
                    bucket['lost'] += 1
                    _example(bucket, row, legacy, canonical, 'lost')
            elif _same(read, legacy, canonical):
                bucket['same'] += 1
            elif read.numeric and _within(read, legacy, canonical):
                bucket['within_tolerance'] += 1
            else:
                bucket['changed'] += 1
                _example(bucket, row, legacy, canonical, 'changed')

    total_lost = sum(f['lost'] for f in summary.values())
    total_changed = sum(f['changed'] for f in summary.values())
    total_placeholders = sum(f['placeholder_dropped'] for f in summary.values())
    if total_lost:
        logger.warning(
            'entity dual-read market_id=%s: %d field(s) would become unknown '
            'under canonical reads; cutover would shrink filter results',
            market_id, total_lost)
    logger.info('entity dual-read market_id=%s vendors=%d changed=%d lost=%d',
                market_id, len(rows), total_changed, total_lost)

    return {'market_id': market_id, 'vendors': len(rows), 'by_field': summary,
            'total_changed': total_changed, 'total_lost': total_lost,
            'total_placeholders_dropped': total_placeholders,
            # Placeholder zeroes disappearing is the fix, so they do not block
            # the cutover. A genuinely lost value does.
            'safe_to_cut_over': total_lost == 0}


def _is_placeholder_zero(field: str, legacy: Any) -> bool:
    """Whether the old value is a zero standing in for a blank cell.

    The registry already decides which fields may legitimately be zero — a
    follower count can be, a headcount cannot — so this asks it rather than
    keeping a second list that would drift.
    """
    from app.services.entity_field_registry import REGISTRY

    read = REGISTRY.get(field)
    if read is None or read.allow_zero:
        return False
    try:
        return float(legacy) == 0
    except (TypeError, ValueError):
        return False


def _same(read: FieldRead, legacy: Any, canonical: Any) -> bool:
    if read.numeric:
        return float(legacy) == float(canonical)
    return str(legacy).strip().lower() == str(canonical).strip().lower()


def _within(read: FieldRead, legacy: Any, canonical: Any) -> bool:
    if not read.tolerance:
        return False
    a, b = float(legacy), float(canonical)
    scale = max(abs(a), abs(b))
    if scale == 0:
        return True
    return abs(a - b) / scale <= read.tolerance


def _example(bucket: Dict[str, Any], row, legacy: Any, canonical: Any,
             kind: str) -> None:
    if len(bucket['examples']) >= 10:
        return
    bucket['examples'].append({
        'brand_id': int(row['brand_id']),
        'display_name': row['display_name'],
        'legacy': _plain(legacy),
        'canonical': _plain(canonical),
        'kind': kind,
    })


def _plain(value: Any) -> Any:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return int(number) if number.is_integer() else number
