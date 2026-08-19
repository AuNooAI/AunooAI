"""The per-theme cutoff that decides new topic vs ongoing topic.

The shipped constant (cosine distance <= 0.85) matched 100% of the corpus —
measured 2026-08-19 on bugfixing, where distances from a real query to 5,000
articles ran 0.072-0.455, median 0.148. So the check decided nothing and every
theme with any older coverage became an ongoing topic.

These tests pin the replacement: a cutoff calibrated from the theme's own
distances and a background sample, corroboration across sources and dates, and
a consistent bias towards llm_proposed when the evidence is thin. That last
part is the one to protect — wrongly calling a genuinely new topic "ongoing"
hides it completely, and nobody sees the absence.
"""

import pytest

from app.services.emerging_topics import historical_cutoff as hc


def candidate(distance, source="wire", day="2026-07-01"):
    return {"distance": distance, "news_source": source, "publication_day": day}


def spread(n, start, step=0.001):
    """A tight cluster of distances, for use as background or theme data."""
    return [start + i * step for i in range(n)]


# ---------------------------------------------------------------------------
# percentile
# ---------------------------------------------------------------------------

def test_percentile_interpolates():
    assert hc.percentile([0.0, 1.0], 0.5) == pytest.approx(0.5)
    assert hc.percentile([0.0, 0.5, 1.0], 0.75) == pytest.approx(0.75)


def test_percentile_handles_edges():
    assert hc.percentile([], 0.5) is None
    assert hc.percentile([0.3], 0.75) == pytest.approx(0.3)
    assert hc.percentile([0.4, 0.1, 0.2], 0.0) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def test_cutoff_is_the_minimum_of_the_three_terms():
    theme = [0.10, 0.11, 0.12, 0.13]          # p75 = 0.1225 -> +0.02 = 0.1425
    background = spread(50, 0.30)             # p10 well above
    cutoff, provisional, p75, p10 = hc.calibrate_cutoff(theme, background)

    assert not provisional
    assert p75 == pytest.approx(0.1225)
    assert cutoff == pytest.approx(0.1425)    # theme term is the tightest


def test_background_p10_binds_when_the_theme_is_loose():
    theme = [0.30, 0.31, 0.32, 0.33]          # p75 + slack = 0.3425
    background = spread(50, 0.05)             # p10 ~ 0.0549
    cutoff, provisional, _, p10 = hc.calibrate_cutoff(theme, background)

    assert not provisional
    assert cutoff == pytest.approx(p10)
    assert cutoff < 0.06, "a close background must tighten the cutoff"


def test_absolute_ceiling_binds_when_both_distributions_are_loose():
    cutoff, provisional, _, _ = hc.calibrate_cutoff(
        spread(10, 0.50), spread(50, 0.60)
    )
    assert not provisional
    assert cutoff == hc.MAX_CUTOFF, "no calibration may exceed the hard ceiling"


def test_thin_theme_data_falls_back_to_the_provisional_cutoff():
    cutoff, provisional, p75, _ = hc.calibrate_cutoff([0.1, 0.1], spread(50, 0.3))
    assert provisional and cutoff == hc.PROVISIONAL_CUTOFF
    assert p75 is None


def test_thin_background_data_falls_back_to_the_provisional_cutoff():
    cutoff, provisional, _, p10 = hc.calibrate_cutoff(spread(10, 0.1), [0.3, 0.4])
    assert provisional and cutoff == hc.PROVISIONAL_CUTOFF
    assert p10 is None


def test_the_provisional_cutoff_is_tighter_than_the_ceiling():
    assert hc.PROVISIONAL_CUTOFF < hc.MAX_CUTOFF


def test_a_degenerate_calibration_does_not_open_the_gate():
    """A zero or negative cutoff would admit nothing; fall back instead."""
    cutoff, provisional, _, _ = hc.calibrate_cutoff(
        spread(10, 0.1), [0.0] * 50
    )
    assert provisional and cutoff == hc.PROVISIONAL_CUTOFF


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def test_the_old_0_85_behaviour_no_longer_classifies_everything_as_ongoing():
    """Distances typical of unrelated articles must not qualify."""
    theme = [0.10, 0.11, 0.12, 0.13]
    background = spread(50, 0.14)
    # Well inside the old 0.85 threshold, nowhere near this theme.
    candidates = [candidate(0.40, f"src{i}", f"2026-07-0{i+1}") for i in range(6)]

    decision = hc.decide(theme, background, candidates)

    assert not decision.is_ongoing
    assert decision.qualifying_articles == 0
    assert "fewer than 3" in decision.reason


def test_genuinely_close_and_corroborated_coverage_is_ongoing():
    theme = [0.10, 0.11, 0.12, 0.13]
    background = spread(50, 0.30)
    candidates = [
        candidate(0.09, "reuters", "2026-07-01"),
        candidate(0.10, "ft", "2026-07-03"),
        candidate(0.11, "bloomberg", "2026-07-05"),
    ]

    decision = hc.decide(theme, background, candidates)

    assert decision.is_ongoing
    assert decision.qualifying_articles == 3
    assert decision.qualifying_sources == 3
    assert decision.qualifying_dates == 3


def test_one_outlet_republishing_is_not_a_history_of_coverage():
    theme = [0.10, 0.11, 0.12, 0.13]
    background = spread(50, 0.30)
    candidates = [candidate(0.09, "wire", f"2026-07-0{i+1}") for i in range(5)]

    decision = hc.decide(theme, background, candidates)

    assert not decision.is_ongoing
    assert decision.qualifying_sources == 1
    assert "single outlet" in decision.reason


def test_one_day_of_coverage_is_a_moment_not_a_history():
    theme = [0.10, 0.11, 0.12, 0.13]
    background = spread(50, 0.30)
    candidates = [
        candidate(0.09, "reuters", "2026-07-01"),
        candidate(0.10, "ft", "2026-07-01"),
        candidate(0.11, "bloomberg", "2026-07-01"),
    ]

    decision = hc.decide(theme, background, candidates)

    assert not decision.is_ongoing
    assert decision.qualifying_dates == 1
    assert "one day of coverage" in decision.reason


def test_two_qualifying_articles_are_not_enough():
    theme = [0.10, 0.11, 0.12, 0.13]
    background = spread(50, 0.30)
    candidates = [
        candidate(0.09, "reuters", "2026-07-01"),
        candidate(0.10, "ft", "2026-07-03"),
        candidate(0.40, "bloomberg", "2026-07-05"),   # too far
    ]

    decision = hc.decide(theme, background, candidates)

    assert not decision.is_ongoing
    assert decision.qualifying_articles == 2


def test_no_candidates_at_all_stays_new():
    decision = hc.decide([0.1] * 5, spread(50, 0.3), [])
    assert not decision.is_ongoing
    assert decision.candidates_examined == 0


def test_thin_calibration_uses_the_provisional_cutoff_and_can_still_decide():
    """Provisional does not mean paralysed — clearly close coverage still counts."""
    candidates = [
        candidate(0.05, "reuters", "2026-07-01"),
        candidate(0.06, "ft", "2026-07-03"),
        candidate(0.07, "bloomberg", "2026-07-05"),
    ]
    decision = hc.decide([], [], candidates)

    assert decision.provisional
    assert decision.cutoff == hc.PROVISIONAL_CUTOFF
    assert decision.is_ongoing


def test_thin_calibration_is_strict_about_middling_distances():
    """Under provisional calibration, borderline coverage stays llm_proposed."""
    candidates = [
        candidate(0.15, "reuters", "2026-07-01"),
        candidate(0.16, "ft", "2026-07-03"),
        candidate(0.17, "bloomberg", "2026-07-05"),
    ]
    decision = hc.decide([], [], candidates)

    assert not decision.is_ongoing, "thin data must err towards a new topic"


def test_the_log_line_reports_qualifying_count_not_retrieval_count():
    theme = [0.10, 0.11, 0.12, 0.13]
    background = spread(50, 0.30)
    candidates = (
        [candidate(0.09, "reuters", "2026-07-01"),
         candidate(0.10, "ft", "2026-07-03"),
         candidate(0.11, "bloomberg", "2026-07-05")]
        + [candidate(0.60, f"far{i}", "2026-07-09") for i in range(57)]
    )

    line = hc.decide(theme, background, candidates).describe()

    assert "3 of 60 historical candidates qualified" in line
    assert "cutoff=" in line
    # The retrieval limit must not be presented as evidence.
    assert "60 historical articles" not in line


def test_the_log_line_names_the_calibration_basis():
    calibrated = hc.decide([0.10, 0.11, 0.12, 0.13], spread(50, 0.30), []).describe()
    assert "p75=" in calibrated and "p10=" in calibrated

    provisional = hc.decide([], [], []).describe()
    assert "provisional" in provisional


def test_decisions_are_deterministic():
    theme = [0.10, 0.11, 0.12, 0.13]
    background = spread(50, 0.30)
    candidates = [candidate(0.09, "reuters", "2026-07-01"),
                  candidate(0.10, "ft", "2026-07-03"),
                  candidate(0.11, "bloomberg", "2026-07-05")]

    lines = {hc.decide(theme, background, candidates).describe() for _ in range(10)}
    assert len(lines) == 1
