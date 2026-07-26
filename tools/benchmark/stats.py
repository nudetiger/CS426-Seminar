#!/usr/bin/env python3
"""Summary statistics for benchmark samples."""

from __future__ import annotations

import math
import statistics
from typing import Sequence


def summarize(values: Sequence[float]) -> dict[str, float | int]:
    """Return mean/median/stdev/min/max/p95 for a non-empty sample list."""
    if not values:
        raise ValueError("Cannot summarize an empty sample list")

    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    mean = statistics.fmean(ordered)
    median = statistics.median(ordered)
    stdev = statistics.stdev(ordered) if n >= 2 else 0.0
    p95 = _percentile(ordered, 95.0)
    return {
        "n": n,
        "mean": mean,
        "median": median,
        "stdev": stdev,
        "min": ordered[0],
        "max": ordered[-1],
        "p95": p95,
    }


def _percentile(ordered: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile on a pre-sorted ascending sequence."""
    if not ordered:
        raise ValueError("empty")
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return float(ordered[low]) * (1.0 - weight) + float(ordered[high]) * weight
