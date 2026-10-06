"""scripts/brand_relevance_eval.py: the scoring arithmetic. No database."""
import importlib.util
import os

import pytest

spec = importlib.util.spec_from_file_location(
    "bre", os.path.join(os.path.dirname(__file__), "..", "scripts", "brand_relevance_eval.py"))
bre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bre)


def _meta(rows, pop):
    return {"site": "s", "brand": "B", "window_days": 30, "drawn": "2026-10-06", "sampling": "x",
            "population": pop, "rows": rows}


def _r(uri, stratum):
    return {"uri": uri, "stratum": stratum, "system_earned": stratum == "included"}


def test_counts_precision_recall_and_weights():
    rows = [_r("a", "included"), _r("b", "included"), _r("c", "rejected_named"), _r("d", "rejected_named"),
            _r("e", "rejected_unnamed"), _r("f", "included")]
    pop = {"included": 30, "rejected_named": 100, "rejected_unnamed": 500, "undecided": 10}
    ans = {"a": "coverage", "b": "not_coverage", "c": "coverage", "d": "sector", "e": "not_coverage",
           "f": "cannot_tell"}
    s = bre.score(_meta(rows, pop), ans)
    assert s["counts"] == {"TP": 1, "FP": 1, "FN": 1, "TN": 2, "cannot_tell": 1, "unanswered": 0}
    assert s["precision"] == 0.5 and s["recall"] == 0.5
    # Weights: included 30/3 = 10 per row, rejected_named 100/2 = 50 per row.
    assert s["precision_weighted"] == pytest.approx(0.5)
    assert s["recall_weighted"] == pytest.approx(10 / 60)
    assert s["availability"] == pytest.approx(1 - 10 / 640)


def test_missing_denominator_is_unavailable_not_zero():
    s = bre.score(_meta([_r("a", "rejected_unnamed")], {"rejected_unnamed": 5}), {"a": "not_coverage"})
    assert s["precision"] is None and s["recall"] is None and s["precision_ci"] is None
    assert bre._fmt(None) == "unavailable"


def test_unanswered_rows_are_reported_not_guessed():
    s = bre.score(_meta([_r("a", "included")], {"included": 1}), {})
    assert s["counts"]["unanswered"] == 1 and s["precision"] is None


def test_wilson_interval_bounds():
    lo, hi = bre.wilson(18, 20)
    assert 0.6 < lo < 0.9 < hi <= 1.0
    assert bre.wilson(0, 0) is None
