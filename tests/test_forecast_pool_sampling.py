"""The assessment pool is sampled evenly so the reranker's pair ceiling
never leaves every article unassigned."""
from app.services.forecast_assessment_service import _even_sample


def test_small_pool_is_untouched():
    rows = list(range(10))
    assert _even_sample(rows, 50) == rows


def test_sample_has_requested_size_and_keeps_order():
    rows = list(range(2000))
    out = _even_sample(rows, 300)
    assert len(out) == 300
    assert out == sorted(out)


def test_sample_spans_the_whole_window():
    rows = list(range(2000))
    out = _even_sample(rows, 300)
    # Newest-first input: the sample must reach the oldest end, not stop
    # after the first 300 rows.
    assert out[0] == 0
    assert out[-1] > 1900


def test_zero_target_gives_empty_pool():
    assert _even_sample(list(range(5)), 0) == []
