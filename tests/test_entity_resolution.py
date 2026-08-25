"""Entity resolution — the refusals that keep a vendor page honest.

These are pure tests. The ranking, the conflict rule, the consensus vote and
the value coercion all work on plain dictionaries, so the interesting failures
can be pinned without a database and without a provider.

Each test here corresponds to a way the old registry got something wrong. A
provider that stopped answering used to blank a field. A workbook headcount of
zero used to be displayed as a headcount of zero. Crunchbase, which carries no
funding total at all, used to be able to look like it had supplied one. Those
are the cases below.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import entity_resolution as er
from app.services.entity_field_registry import (
    ConflictRule, coerce, policy, typed_columns,
)

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def obs(id_, source, value, *, authority=None, days_ago=0, confidence=None,
        metadata=None, field='employee_count'):
    """One observation row in the shape the resolver reads."""
    p = policy(field)
    return {
        'id': id_, 'source': source, 'value_json': value,
        'authority': authority if authority is not None else p.authority_of(source),
        'observed_at': NOW - timedelta(days=days_ago), 'effective_at': None,
        'confidence': confidence, 'metadata': metadata or {},
    }


# ---------------------------------------------------------------------------
# Values that are not values
# ---------------------------------------------------------------------------

def test_zero_headcount_is_not_a_headcount():
    """The workbook writes 0 for a blank cell. A company with no staff is not
    a company, and the review queue is full of tasks caused by displaying it."""
    assert coerce('employee_count', 0) is None
    assert coerce('employee_count', None) is None
    assert coerce('employee_count', '') is None
    assert coerce('employee_count', 90) == 90


def test_zero_followers_is_a_real_reading():
    """Unlike headcount, a genuinely new company page can have no followers."""
    assert coerce('followers_linkedin', 0) == 0


def test_unknown_funding_never_becomes_zero():
    assert coerce('funding_total_musd', None) is None
    assert coerce('funding_total_musd', 0) is None
    assert coerce('funding_total_musd', 45.0) == 45.0


def test_crunchbase_may_not_answer_funding_total():
    """The mapped dataset has no amount in it. Letting the source through
    would turn 'we did not get a figure' into a dollar value on a page."""
    p = policy('funding_total_musd')
    assert not p.accepts('crunchbase_company')
    assert p.accepts('pitchbook_company')
    assert p.accepts('workbook')


def test_workbook_may_not_answer_follower_count():
    assert not policy('followers_linkedin').accepts('workbook')


def test_typed_column_split_matches_the_declared_type():
    text_v, number_v, date_v, unit = typed_columns('employee_count', 310)
    assert (text_v, number_v, date_v, unit) == (None, 310.0, None, 'people')
    text_v, number_v, date_v, _ = typed_columns('hq_country', 'Israel')
    assert (text_v, number_v, date_v) == ('Israel', None, None)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def test_verified_source_outranks_linkedin_which_outranks_workbook():
    """Workbook 180, LinkedIn 296, verified PitchBook 310 -> 310 wins, and
    the other two are still there to be shown beside it."""
    candidates = [
        obs(1, 'workbook', 180, days_ago=120),
        obs(2, 'linkedin_company_profile', 296, days_ago=10),
        obs(3, 'pitchbook_company', 310, days_ago=5,
            metadata={'verified': True}),
    ]
    p = policy('employee_count')
    eligible = [c for c in candidates if er._eligible(c, p)]
    winner = max(eligible, key=er._rank_key)
    assert winner['id'] == 3
    assert len(eligible) == 3


def test_unverified_pitchbook_is_stored_but_not_used():
    """The PitchBook mapping has never been checked against a live response,
    so its readings wait for that rather than deciding a customer-facing
    number."""
    p = policy('employee_count')
    unverified = obs(1, 'pitchbook_company', 310)
    assert er._eligible(unverified, p) is False
    verified = obs(2, 'pitchbook_company', 310, metadata={'verified': True})
    assert er._eligible(verified, p) is True


def test_ranking_is_deterministic_for_identical_candidates():
    """Same authority, same instant: the id decides, so a replay cannot
    produce a different winner."""
    a = obs(7, 'linkedin_company_profile', 100)
    b = obs(8, 'linkedin_company_profile', 100)
    assert max([a, b], key=er._rank_key)['id'] == 8
    assert max([b, a], key=er._rank_key)['id'] == 8


def test_recency_breaks_ties_within_one_source():
    old = obs(1, 'linkedin_company_profile', 250, days_ago=30)
    new = obs(2, 'linkedin_company_profile', 296, days_ago=1)
    assert max([old, new], key=er._rank_key)['id'] == 2


# ---------------------------------------------------------------------------
# Consensus, for fields that should stop moving
# ---------------------------------------------------------------------------

def test_founded_year_follows_the_weight_of_agreement():
    """Two sources saying 2021 beat one stronger source saying 2019, so the
    year does not flip every time a collection run lands."""
    candidates = [
        obs(1, 'workbook', 2021, field='founded_year'),
        obs(2, 'linkedin_company_profile', 2021, field='founded_year'),
        obs(3, 'crunchbase_company', 2019, field='founded_year',
            metadata={'verified': True}),
    ]
    assert er._consensus_winner(candidates)['value_json'] == 2021


def test_one_source_repeating_itself_is_not_a_consensus():
    """Three readings from one provider are one opinion, so its authority is
    counted once rather than three times."""
    candidates = [
        obs(1, 'workbook', 2021, field='founded_year', days_ago=3),
        obs(2, 'workbook', 2021, field='founded_year', days_ago=2),
        obs(3, 'workbook', 2021, field='founded_year', days_ago=1),
        obs(4, 'pitchbook_company', 2018, field='founded_year',
            metadata={'verified': True}),
    ]
    assert er._consensus_winner(candidates)['value_json'] == 2018


# ---------------------------------------------------------------------------
# Conflict
# ---------------------------------------------------------------------------

def test_a_year_apart_is_tolerated_and_three_years_is_a_conflict():
    p = policy('founded_year')
    assert p.conflict.disagrees(2021, 2022) is False
    assert p.conflict.disagrees(2021, 2024) is True


def test_countries_conflict_on_any_difference():
    assert policy('hq_country').conflict.disagrees('Israel', 'United States')
    assert not policy('hq_country').conflict.disagrees('israel', 'Israel')


def test_a_weak_source_disagreeing_is_not_a_conflict():
    """The workbook losing to LinkedIn is the system working, not a dispute
    to put in front of an operator."""
    p = policy('employee_count')
    winner = obs(1, 'linkedin_company_profile', 296, days_ago=1)
    candidates = [winner, obs(2, 'workbook', 180, days_ago=1)]
    assert er._find_rival(candidates, winner, p) is None


def test_two_strong_fresh_sources_disagreeing_is_a_conflict():
    p = policy('employee_count')
    winner = obs(1, 'pitchbook_company', 310, days_ago=1,
                 metadata={'verified': True})
    rival = obs(2, 'zoominfo_company', 120, days_ago=1,
                metadata={'verified': True})
    assert er._find_rival([winner, rival], winner, p)['id'] == 2


def test_different_measurements_are_not_a_disagreement():
    """A LinkedIn profile headcount and a total workforce estimate are both
    honest and are not the same number, so they are compared, never merged."""
    p = policy('employee_count')
    assert p.series_of('linkedin_company_profile') != p.series_of('pitchbook_company')
    winner = obs(1, 'linkedin_company_profile', 296, days_ago=1)
    other = obs(2, 'pitchbook_company', 180, days_ago=1,
                metadata={'verified': True})
    assert er._find_rival([winner, other], winner, p) is None


def test_a_stale_rival_does_not_raise_a_conflict():
    p = policy('employee_count')
    winner = obs(1, 'linkedin_company_profile', 296, days_ago=1)
    ancient = obs(2, 'zoominfo_company', 90, days_ago=900,
                  metadata={'verified': True})
    assert er._find_rival([winner, ancient], winner, p) is None


def test_relative_tolerance_scales_with_the_number():
    rule = ConflictRule('relative', 0.25)
    assert rule.disagrees(100, 120) is False
    assert rule.disagrees(100, 200) is True
    assert rule.disagrees(0, 0) is False


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

def test_taxonomy_is_market_scoped_and_analyst_controlled():
    p = policy('market_category')
    assert p.scope == 'market'
    assert p.membership_column == 'category'
    # No provider may reclassify a market's own map.
    assert not p.accepts('linkedin_company_profile')
    assert not p.accepts('crunchbase_company')
    assert p.accepts('manual')


def test_company_facts_are_not_market_scoped():
    assert policy('employee_count').scope == 'entity'
    assert policy('employee_count').profile_column == 'employee_count'


def test_unknown_field_raises_rather_than_defaulting():
    with pytest.raises(KeyError):
        policy('revenue')
