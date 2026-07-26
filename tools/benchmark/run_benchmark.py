#!/usr/bin/env python3
"""
Automated gallery benchmark runner (host-side).

Drives the installed CS426 gallery app over adb, reads GalleryBench log markers and
dumpsys metrics, then writes per-run and summary CSV files.

Requires: Python 3.9+, adb on PATH, unlocked device/emulator with the app installed.
Stdlib only — no pip packages required.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python tools/benchmark/run_benchmark.py` from repo root.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import adb_util
from csv_export import write_runs_csv, write_summary_csv
from scenarios import ALL_SCENARIOS, SCENARIOS, BenchConfig

REPO_ROOT = _SCRIPT_DIR.parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "benchmark"
DEFAULT_PACKAGE = "com.cs426.gallery"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run automated CS426 gallery benchmarks and export CSV results.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Measured iterations per scenario (default: 10).",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Warmup iterations discarded before measurement (default: 1).",
    )
    parser.add_argument(
        "--scenarios",
        default=",".join(ALL_SCENARIOS),
        help=f"Comma-separated scenarios (default: all). Choices: {', '.join(ALL_SCENARIOS)}",
    )
    parser.add_argument(
        "--dataset",
        choices=("easy", "mixed"),
        default="mixed",
        help="Dataset label for CSV; also used with --install (default: mixed).",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Build and install debug APK with -PgalleryDataset=<dataset> before running.",
    )
    parser.add_argument(
        "--package",
        default=DEFAULT_PACKAGE,
        help=f"Application id (default: {DEFAULT_PACKAGE}).",
    )
    parser.add_argument(
        "--tag",
        default="untagged",
        help="Label written into CSV rows (e.g. v1-unoptimized).",
    )
    parser.add_argument(
        "--preview-index",
        type=int,
        default=0,
        help="Zero-based gallery index to open for preview scenarios (default: 0).",
    )
    parser.add_argument(
        "--swipe-count",
        type=int,
        default=5,
        help="Next-arrow navigations per swipe_preview iteration (default: 5).",
    )
    parser.add_argument(
        "--scroll-flings",
        type=int,
        default=8,
        help="Swipe gestures per scroll_gallery iteration (default: 8).",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=180.0,
        help="Per-wait timeout for GalleryBench events (default: 180).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for CSV output (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--output-prefix",
        default=None,
        help="Filename prefix for CSVs (default: <tag>_<dataset>_<timestamp>).",
    )
    return parser.parse_args(argv)


def gradlew_cmd() -> list[str]:
    if os.name == "nt":
        script = REPO_ROOT / "gradlew.bat"
        if script.exists():
            return [str(script)]
    script = REPO_ROOT / "gradlew"
    if script.exists():
        # On Windows without .bat, still try via cmd if present
        if os.name == "nt":
            return ["cmd", "/c", str(script)]
        return [str(script)]
    return ["gradle"]


def install_app(dataset: str) -> None:
    cmd = [
        *gradlew_cmd(),
        ":app:installDebug",
        f"-PgalleryDataset={dataset}",
    ]
    print(f"Installing app: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    if completed.returncode != 0:
        raise SystemExit(f"Gradle installDebug failed with exit {completed.returncode}")


def resolve_scenarios(raw: str) -> list[str]:
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise SystemExit("No scenarios selected")
    unknown = [name for name in names if name not in SCENARIOS]
    if unknown:
        raise SystemExit(
            f"Unknown scenario(s): {', '.join(unknown)}. "
            f"Valid: {', '.join(ALL_SCENARIOS)}"
        )
    return names


def default_prefix(tag: str, dataset: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tag = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tag)
    return f"{safe_tag}_{dataset}_{stamp}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.iterations < 1:
        raise SystemExit("--iterations must be >= 1")
    if args.warmup < 0:
        raise SystemExit("--warmup must be >= 0")

    scenarios = resolve_scenarios(args.scenarios)
    adb_util.require_device()

    if args.install:
        install_app(args.dataset)

    cfg = BenchConfig(
        package=args.package,
        tag=args.tag,
        dataset=args.dataset,
        timeout_sec=args.timeout_sec,
        preview_index=args.preview_index,
        swipe_count=args.swipe_count,
        scroll_flings=args.scroll_flings,
    )

    prefix = args.output_prefix or default_prefix(args.tag, args.dataset)
    output_dir: Path = args.output_dir
    runs_path = output_dir / f"{prefix}_runs.csv"
    summary_path = output_dir / f"{prefix}_summary.csv"

    rows: list[dict] = []
    total_iters = args.warmup + args.iterations

    print(
        f"Benchmark tag={cfg.tag} dataset={cfg.dataset} "
        f"scenarios={scenarios} warmup={args.warmup} iterations={args.iterations}"
    )

    for scenario in scenarios:
        runner = SCENARIOS[scenario]
        print(f"\n=== Scenario: {scenario} ===")
        for i in range(total_iters):
            is_warmup = i < args.warmup
            measured_iteration = -1 if is_warmup else (i - args.warmup)
            label = "warmup" if is_warmup else f"iter {measured_iteration + 1}/{args.iterations}"
            print(f"  [{label}] running…", flush=True)
            try:
                if is_warmup:
                    # Run but discard samples.
                    discard: list[dict] = []
                    runner(cfg, -1, discard)
                else:
                    runner(cfg, measured_iteration, rows)
            except adb_util.AdbError as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)
                # Continue other iterations; leave a gap rather than aborting the whole suite.
                continue
            time.sleep(0.25)

    if not rows:
        raise SystemExit("No samples collected; check device logs and app install.")

    write_runs_csv(runs_path, rows)
    write_summary_csv(summary_path, rows, tag=cfg.tag, dataset=cfg.dataset)

    print(f"\nWrote {len(rows)} samples:")
    print(f"  {runs_path}")
    print(f"  {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
