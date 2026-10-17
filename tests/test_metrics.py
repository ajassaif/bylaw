import pytest

from bylaw.metrics import (accuracy, bootstrap_ci, brier_binary, ece, false_proceed_rate, latency_pcts, macro_f1,
                           risk_coverage)

Y = ["proceed", "deny", "guide", "deny"]
P = ["proceed", "deny", "proceed", "confirm"]


def test_accuracy():
    assert accuracy(Y, P) == 0.5
    assert accuracy(["deny"] * 4, ["deny", "deny", "deny", "guide"]) == 0.75


def test_macro_f1():
    # proceed: tp1 fp1 fn0 -> f1 2/3; deny: tp1 fp0 fn1 -> 2/3; guide: tp0 fn1 -> 0; confirm: fp1 -> 0
    assert macro_f1(Y, P) == pytest.approx((2 / 3 + 2 / 3 + 0 + 0) / 4)
    assert macro_f1(["deny"], ["deny"]) == 1.0  # labels with no support and no predictions are skipped


def test_false_proceed_rate():
    assert false_proceed_rate(Y, P) == pytest.approx(1 / 3)
    assert false_proceed_rate(["proceed"], ["proceed"]) == 0.0


def test_ece_perfect_and_overconfident():
    assert ece([1.0, 1.0, 0.0], [True, True, False]) == pytest.approx(0.0)
    assert ece([0.9] * 10, [True] * 5 + [False] * 5) == pytest.approx(0.4)


def test_brier_binary():
    assert brier_binary([1.0, 0.0], [True, False]) == 0.0
    assert brier_binary([0.5], [True]) == 0.25


def test_risk_coverage_starts_with_most_confident():
    rc = risk_coverage([0.2, 0.9, 0.6], [False, True, False])
    assert rc[0] == (pytest.approx(1 / 3), 1.0)
    assert rc[-1] == (1.0, pytest.approx(1 / 3))


def test_bootstrap_ci_brackets_point_estimate():
    correct = [True] * 70 + [False] * 30
    lo, hi = bootstrap_ci(lambda idx: sum(correct[i] for i in idx) / len(idx), len(correct))
    assert lo < 0.7 < hi
    assert 0.55 < lo and hi < 0.85


def test_latency_pcts():
    out = latency_pcts([100, 200, 300, 400, 1000])
    assert out["p50"] == 300 and out["mean"] == 400
    assert 400 < out["p95"] <= 1000
    assert latency_pcts([]) == {"p50": None, "p95": None, "mean": None}
