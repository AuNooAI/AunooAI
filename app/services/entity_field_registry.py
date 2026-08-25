"""What each company field means, and which source is allowed to answer it.

Resolution cannot run off a single ranked list of sources, because the right
answer depends on the question. LinkedIn is the best available source for a
follower count and a poor one for a funding total. Crunchbase's mapped dataset
carries no reliable dollar amount at all, so for ``funding_total_musd`` it is
not a weak source — it is not a source. The workbook is the weakest source for
almost everything and is still the only one that has ever answered some fields.

So the registry is per field: which sources may answer it, how fresh an answer
has to be, how far two answers may differ before that is a disagreement rather
than noise, and whether an automatic reading is allowed to displace something a
person typed.

Three rules run through all of it.

A null never wins. An absent field in a provider payload means the provider did
not say, and "did not say" must not overwrite "we know".

Zero is not a small number here. A headcount of zero and an unknown headcount
look identical in a spreadsheet and mean completely different things, so zero
is rejected for every field whose policy does not explicitly permit it.

Market taxonomy is not a company fact. Category and sub-category describe a
company's place in one market's map, they are set by an analyst, and no
provider reading may reclassify them.

Bump ``ENTITY_FIELD_POLICY_VERSION`` whenever a policy below changes meaning.
Canonical rows record the version that chose them, so a later replay can
explain why an answer moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Dict, FrozenSet, Optional, Tuple

ENTITY_FIELD_POLICY_VERSION = '1.0'

# Scope: a global company fact, or a fact about one market membership.
SCOPE_ENTITY = 'entity'
SCOPE_MARKET = 'market'

DAY = 86400


@dataclass(frozen=True)
class ConflictRule:
    """How far two credible fresh answers may differ before we say so.

    ``kind`` is one of:

    - ``exact``    — any difference is a conflict (country, status)
    - ``absolute`` — differ by more than ``threshold`` units (founded year)
    - ``relative`` — differ by more than ``threshold`` as a fraction
    - ``none``     — differences are expected; the newest simply wins
    """
    kind: str = 'none'
    threshold: float = 0.0

    def disagrees(self, a, b) -> bool:
        if self.kind == 'none':
            return False
        if self.kind == 'exact':
            return str(a).strip().lower() != str(b).strip().lower()
        try:
            x, y = float(a), float(b)
        except (TypeError, ValueError):
            return str(a).strip().lower() != str(b).strip().lower()
        if self.kind == 'absolute':
            return abs(x - y) > self.threshold
        if self.kind == 'relative':
            scale = max(abs(x), abs(y))
            if scale == 0:
                return False
            return abs(x - y) / scale > self.threshold
        return False


@dataclass(frozen=True)
class FieldPolicy:
    key: str
    scope: str
    value_type: str                       # text | integer | number | date | json
    strategy: str
    authority: Dict[str, int]             # source -> 0..100, and the allow-list
    unit: Optional[str] = None
    verified_only: FrozenSet[str] = frozenset()
    stale_after_seconds: Optional[int] = None
    conflict: ConflictRule = ConflictRule()
    automated_may_replace_manual: bool = False
    automated_may_replace_import: bool = True
    allow_zero: bool = False
    allow_decrease: bool = True
    decrease_review_ratio: Optional[float] = None
    # Sources measuring different things must not be plotted as one series,
    # even when both are honest. LinkedIn's employee count and a total
    # workforce estimate are both headcounts and are not the same number.
    measurement_class: Dict[str, str] = _dc_field(default_factory=dict)
    profile_column: Optional[str] = None      # bw_entity_profiles
    membership_column: Optional[str] = None   # bw_market_brands
    self_reported: bool = False

    def accepts(self, source: str) -> bool:
        return source in self.authority

    def authority_of(self, source: str) -> int:
        return self.authority.get(source, 0)

    def series_of(self, source: str) -> str:
        return self.measurement_class.get(source, source)


# Baseline authority. A field may narrow this, and several do.
_A_MANUAL = 95
_A_PITCHBOOK = 85
_A_ZOOMINFO = 70
_A_CRUNCHBASE = 65
_A_LINKEDIN = 60
_A_VENDOR_WEB = 55
_A_WORKBOOK = 40


REGISTRY: Dict[str, FieldPolicy] = {
    # ---------------------------------------------------------------- entity
    'hq_country': FieldPolicy(
        key='hq_country', scope=SCOPE_ENTITY, value_type='text',
        strategy='latest_credible',
        # Headquarters, not country of founding. A company that moved has one
        # correct answer and it is the current one.
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'zoominfo_company': _A_ZOOMINFO,
                   'crunchbase_company': _A_CRUNCHBASE,
                   'linkedin_company_profile': _A_LINKEDIN,
                   'vendor_web': _A_VENDOR_WEB, 'workbook': _A_WORKBOOK},
        verified_only=frozenset({'pitchbook_company', 'zoominfo_company'}),
        stale_after_seconds=365 * DAY,
        conflict=ConflictRule('exact'),
        profile_column='hq_country',
    ),
    'founded_year': FieldPolicy(
        key='founded_year', scope=SCOPE_ENTITY, value_type='integer',
        strategy='stable_consensus',
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'crunchbase_company': _A_CRUNCHBASE,
                   'linkedin_company_profile': _A_LINKEDIN,
                   'workbook': _A_WORKBOOK},
        verified_only=frozenset({'pitchbook_company', 'crunchbase_company'}),
        # A founding year does not change. Once settled it should stop moving,
        # so a one-year disagreement is tolerated and anything wider is a
        # conflict rather than a silent flip between two sources.
        conflict=ConflictRule('absolute', 1),
        profile_column='founded_year',
    ),
    'employee_count': FieldPolicy(
        key='employee_count', scope=SCOPE_ENTITY, value_type='integer',
        unit='people', strategy='latest_fresh',
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'zoominfo_company': _A_ZOOMINFO,
                   'linkedin_company_profile': _A_LINKEDIN,
                   'workbook': _A_WORKBOOK},
        verified_only=frozenset({'pitchbook_company', 'zoominfo_company'}),
        stale_after_seconds=180 * DAY,
        conflict=ConflictRule('relative', 0.25),
        # Zero staff is not a company. It is the shape of a missing field, and
        # the review queue already carries tasks created by exactly that.
        allow_zero=False,
        decrease_review_ratio=0.40,
        measurement_class={
            'linkedin_company_profile': 'linkedin_profile_headcount',
            'pitchbook_company': 'total_headcount',
            'zoominfo_company': 'total_headcount',
            'workbook': 'import_estimate',
            'manual': 'verified_headcount',
        },
        profile_column='employee_count',
    ),
    'followers_linkedin': FieldPolicy(
        key='followers_linkedin', scope=SCOPE_ENTITY, value_type='integer',
        unit='followers', strategy='latest_fresh',
        # Only LinkedIn knows this, and the workbook must never supply it.
        authority={'linkedin_company_profile': _A_LINKEDIN,
                   'manual': _A_MANUAL},
        stale_after_seconds=7 * DAY,
        allow_zero=True,
        profile_column='followers_linkedin',
    ),
    'funding_total_musd': FieldPolicy(
        key='funding_total_musd', scope=SCOPE_ENTITY, value_type='number',
        unit='musd', strategy='authoritative_amount',
        # Crunchbase is absent on purpose. The mapped dataset carries no
        # reliable total, so letting it answer this field would turn "we did
        # not get an amount" into a dollar figure on a customer-facing page.
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'workbook': _A_WORKBOOK},
        verified_only=frozenset({'pitchbook_company'}),
        conflict=ConflictRule('relative', 0.05),
        # Totals accumulate. A smaller number is either a correction or a
        # mistake, and the two are told apart by a person, not by recency.
        allow_decrease=False,
        allow_zero=False,
        profile_column='funding_total_musd',
    ),
    'funding_status': FieldPolicy(
        key='funding_status', scope=SCOPE_ENTITY, value_type='text',
        strategy='latest_credible',
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'crunchbase_company': _A_CRUNCHBASE,
                   'workbook': _A_WORKBOOK},
        conflict=ConflictRule('exact'),
        profile_column='funding_status',
    ),
    'last_funding_type': FieldPolicy(
        key='last_funding_type', scope=SCOPE_ENTITY, value_type='text',
        strategy='latest_dated',
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'crunchbase_company': _A_CRUNCHBASE,
                   'workbook': _A_WORKBOOK},
        verified_only=frozenset({'pitchbook_company'}),
        conflict=ConflictRule('exact'),
        profile_column='last_funding_type',
    ),
    'operating_status': FieldPolicy(
        key='operating_status', scope=SCOPE_ENTITY, value_type='text',
        strategy='latest_credible',
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'crunchbase_company': _A_CRUNCHBASE,
                   'linkedin_company_profile': _A_LINKEDIN,
                   'workbook': _A_WORKBOOK},
        conflict=ConflictRule('exact'),
        profile_column='operating_status',
    ),
    'industry': FieldPolicy(
        key='industry', scope=SCOPE_ENTITY, value_type='text',
        strategy='latest_credible',
        authority={'manual': _A_MANUAL, 'pitchbook_company': _A_PITCHBOOK,
                   'zoominfo_company': _A_ZOOMINFO,
                   'linkedin_company_profile': _A_LINKEDIN,
                   'workbook': _A_WORKBOOK},
        # Descriptive and self-selected from a provider's own list. Two
        # sources disagreeing is normal and says nothing about the market map.
        conflict=ConflictRule('none'),
        profile_column='industry',
    ),
    'description': FieldPolicy(
        key='description', scope=SCOPE_ENTITY, value_type='text',
        strategy='latest_credible',
        # How the company describes itself, which is why the owned sources
        # outrank the third-party ones here and nowhere else.
        authority={'manual': _A_MANUAL, 'vendor_web': 80,
                   'linkedin_company_profile': 75,
                   'pitchbook_company': 60, 'zoominfo_company': 55,
                   'crunchbase_company': 50, 'workbook': _A_WORKBOOK},
        conflict=ConflictRule('none'),
        self_reported=True,
        profile_column='description',
    ),
    # --------------------------------------------------------------- market
    # Analyst-controlled. Automated sources may raise a suggestion; the
    # resolver will not move these, which is why only manual and workbook
    # appear and why automated_may_replace_manual stays false.
    'market_category': FieldPolicy(
        key='market_category', scope=SCOPE_MARKET, value_type='text',
        strategy='analyst_controlled',
        authority={'manual': _A_MANUAL, 'workbook': _A_WORKBOOK},
        conflict=ConflictRule('exact'),
        automated_may_replace_import=False,
        membership_column='category',
    ),
    'market_sub_category': FieldPolicy(
        key='market_sub_category', scope=SCOPE_MARKET, value_type='text',
        strategy='analyst_controlled',
        authority={'manual': _A_MANUAL, 'workbook': _A_WORKBOOK},
        conflict=ConflictRule('exact'),
        automated_may_replace_import=False,
        membership_column='sub_category',
    ),
}

# Fields an automated source may propose but never decide.
ANALYST_CONTROLLED = frozenset(
    k for k, p in REGISTRY.items() if p.strategy == 'analyst_controlled')

ENTITY_FIELDS = frozenset(
    k for k, p in REGISTRY.items() if p.scope == SCOPE_ENTITY)
MARKET_FIELDS = frozenset(
    k for k, p in REGISTRY.items() if p.scope == SCOPE_MARKET)


def policy(field_key: str) -> FieldPolicy:
    """The policy for a field. Unknown keys raise rather than defaulting."""
    try:
        return REGISTRY[field_key]
    except KeyError:
        raise KeyError(f"no field policy registered for {field_key!r}") from None


def typed_columns(field_key: str, value) -> Tuple[Optional[str], Optional[float],
                                                  Optional[str], Optional[str]]:
    """Split a value into (value_text, value_number, value_date, unit).

    Exactly one typed column is populated for scalar fields; composite values
    live only in ``value_json``. Callers pass the already-coerced value.
    """
    p = policy(field_key)
    if p.value_type in ('integer', 'number'):
        return None, float(value), None, p.unit
    if p.value_type == 'date':
        return None, None, str(value), p.unit
    if p.value_type == 'json':
        return None, None, None, p.unit
    return str(value), None, None, p.unit


def coerce(field_key: str, value):
    """Coerce a raw source value, or return None when it is not usable.

    Returning None is the normal outcome for a field a provider did not
    answer, and the caller must treat it as "no observation", never as a
    value. Zero passes through only where the policy allows it.
    """
    p = policy(field_key)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if p.value_type in ('integer', 'number'):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number == 0 and not p.allow_zero:
            return None
        if number < 0:
            return None
        return int(number) if p.value_type == 'integer' else number
    if p.value_type == 'text':
        return str(value)
    return value
