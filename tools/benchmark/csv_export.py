#!/usr/bin/env python3
"""CSV writers for gallery benchmark runs and summaries."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from stats import summarize

RUN_FIELDS = [
    "tag",
    "dataset",
    "scenario",
    "metric",
    "unit",
    "iteration",
    "value",
    "timestamp",
]

SUMMARY_FIELDS = [
    "tag",
    "dataset",
    "scenario",
    "metric",
    "unit",
    "n",
    "mean",
    "median",
    "stdev",
    "min",
    "max",
    "p95",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_runs_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUN_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in RUN_FIELDS})


def write_summary_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    tag: str,
    dataset: str,
) -> None:
    """
    Aggregate run rows by (scenario, metric, unit) into summary statistics.
    Only rows with numeric ``value`` and non-negative ``iteration`` are included.
    """
    buckets: dict[tuple[str, str, str], list[float]] = {}
    for row in rows:
        try:
            iteration = int(row["iteration"])
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if iteration < 0:
            # Warmup sentinel if ever used
            continue
        key = (str(row["scenario"]), str(row["metric"]), str(row["unit"]))
        buckets.setdefault(key, []).append(value)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for (scenario, metric, unit), values in sorted(buckets.items()):
            stats = summarize(values)
            writer.writerow(
                {
                    "tag": tag,
                    "dataset": dataset,
                    "scenario": scenario,
                    "metric": metric,
                    "unit": unit,
                    "n": stats["n"],
                    "mean": f"{stats['mean']:.4f}",
                    "median": f"{stats['median']:.4f}",
                    "stdev": f"{stats['stdev']:.4f}",
                    "min": f"{stats['min']:.4f}",
                    "max": f"{stats['max']:.4f}",
                    "p95": f"{stats['p95']:.4f}",
                }
            )


def make_run_row(
    *,
    tag: str,
    dataset: str,
    scenario: str,
    metric: str,
    unit: str,
    iteration: int,
    value: float,
    timestamp: str | None = None,
) -> dict[str, object]:
    return {
        "tag": tag,
        "dataset": dataset,
        "scenario": scenario,
        "metric": metric,
        "unit": unit,
        "iteration": iteration,
        "value": f"{value:.4f}",
        "timestamp": timestamp or utc_now_iso(),
    }
