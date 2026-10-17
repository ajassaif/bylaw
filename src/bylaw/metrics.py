"""Benchmark metrics. Small, dependency-free, and tested against hand-computed examples."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence

from bylaw.pack import ACTIONS


def accuracy(y: Sequence[str], p: Sequence[str]) -> float:
    return sum(a == b for a, b in zip(y, p, strict=True)) / len(y) if y else 0.0


def macro_f1(y: Sequence[str], p: Sequence[str], labels: Sequence[str] = ACTIONS) -> float:
    scores = []
    for label in labels:
        tp = sum(a == label and b == label for a, b in zip(y, p, strict=True))
        fp = sum(a != label and b == label for a, b in zip(y, p, strict=True))
        fn = sum(a == label and b != label for a, b in zip(y, p, strict=True))
        if tp + fp + fn == 0:
            continue
        scores.append(2 * tp / (2 * tp + fp + fn))
    return sum(scores) / len(scores) if scores else 0.0


def false_proceed_rate(y: Sequence[str], p: Sequence[str]) -> float:
    """Of the cases that should not have run, the share that would have run anyway."""
    bad = [b for a, b in zip(y, p, strict=True) if a != "proceed"]
    return sum(b == "proceed" for b in bad) / len(bad) if bad else 0.0


def ece(conf: Sequence[float], correct: Sequence[bool], bins: int = 10) -> float:
    """Top-label expected calibration error over equal-width bins."""
    if not conf:
        return 0.0
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for c, ok in zip(conf, correct, strict=True):
        buckets[min(int(c * bins), bins - 1)].append((c, ok))
    total = len(conf)
    return sum(abs(sum(ok for _, ok in b) / len(b) - sum(c for c, _ in b) / len(b)) * len(b) / total
               for b in buckets if b)


def brier_binary(prob: Sequence[float], outcome: Sequence[bool]) -> float:
    return sum((q - float(o)) ** 2 for q, o in zip(prob, outcome, strict=True)) / len(prob) if prob else 0.0


def risk_coverage(conf: Sequence[float], correct: Sequence[bool]) -> list[tuple[float, float]]:
    """(coverage, accuracy) when only the k most confident answers are kept, for k = 1..n."""
    ranked = sorted(zip(conf, correct, strict=True), key=lambda t: -t[0])
    out, hits = [], 0
    for k, (_, ok) in enumerate(ranked, start=1):
        hits += ok
        out.append((k / len(ranked), hits / k))
    return out


def bootstrap_ci(stat: Callable[[list[int]], float], n: int, iters: int = 2000, seed: int = 7) -> tuple[float, float]:
    """95% percentile interval of `stat` over resampled case indices."""
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    values = sorted(stat([rng.randrange(n) for _ in range(n)]) for _ in range(iters))
    return values[int(0.025 * iters)], values[min(iters - 1, int(0.975 * iters))]


def _quantile(sorted_vals: list[float], q: float) -> float:
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def latency_pcts(ms: Sequence[float]) -> dict:
    if not ms:
        return {"p50": None, "p95": None, "mean": None}
    vals = sorted(float(m) for m in ms)
    return {"p50": _quantile(vals, 0.5), "p95": _quantile(vals, 0.95), "mean": sum(vals) / len(vals)}
