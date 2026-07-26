#!/usr/bin/env python3
"""Benchmark scenarios driven over adb."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Callable

import adb_util
from csv_export import make_run_row, utc_now_iso

JANK_THRESHOLD_MS = 16.6667
MAIN_ACTIVITY = "com.cs426.gallery/.MainActivity"


@dataclass
class BenchConfig:
    package: str
    tag: str
    dataset: str
    timeout_sec: float
    preview_index: int
    swipe_count: int
    scroll_flings: int


def _emit(
    rows: list[dict],
    cfg: BenchConfig,
    scenario: str,
    metric: str,
    unit: str,
    iteration: int,
    value: float,
) -> None:
    rows.append(
        make_run_row(
            tag=cfg.tag,
            dataset=cfg.dataset,
            scenario=scenario,
            metric=metric,
            unit=unit,
            iteration=iteration,
            value=value,
            timestamp=utc_now_iso(),
        )
    )


def ensure_gallery_ready(cfg: BenchConfig, *, force_cold: bool = False) -> dict[str, str]:
    if force_cold:
        adb_util.force_stop(cfg.package)
        time.sleep(0.4)
    adb_util.clear_logcat()
    adb_util.start_activity(MAIN_ACTIVITY)
    return adb_util.wait_for_bench_event("gallery_ready", timeout_sec=cfg.timeout_sec)


def run_cold_startup(cfg: BenchConfig, iteration: int, rows: list[dict]) -> None:
    adb_util.force_stop(cfg.package)
    time.sleep(0.5)
    adb_util.clear_logcat()
    adb_util.start_activity(MAIN_ACTIVITY)
    fields = adb_util.wait_for_bench_event("gallery_ready", timeout_sec=cfg.timeout_sec)
    elapsed = float(fields.get("elapsed_ms", "nan"))
    _emit(rows, cfg, "cold_startup", "duration_ms", "ms", iteration, elapsed)


def run_open_preview(cfg: BenchConfig, iteration: int, rows: list[dict]) -> None:
    ensure_gallery_ready(cfg, force_cold=True)
    # Manifest ids are typically 1-based sequential; content-desc uses image id.
    # Prefer tapping by index order: "Gallery image {id}" where id ≈ index+1 for generators.
    image_id = cfg.preview_index + 1
    desc = f"Gallery image {image_id}"
    adb_util.clear_logcat()
    adb_util.tap_content_desc(exact=desc)
    fields = adb_util.wait_for_bench_event("preview_ready", timeout_sec=cfg.timeout_sec)
    elapsed = float(fields.get("elapsed_ms", "nan"))
    _emit(rows, cfg, "open_preview", "duration_ms", "ms", iteration, elapsed)


def run_swipe_preview(cfg: BenchConfig, iteration: int, rows: list[dict]) -> None:
    # Start mid-gallery so Next remains available for swipe_count steps.
    start_index = max(0, cfg.preview_index)
    ensure_gallery_ready(cfg, force_cold=True)
    image_id = start_index + 1
    adb_util.clear_logcat()
    adb_util.tap_content_desc(exact=f"Gallery image {image_id}")
    adb_util.wait_for_bench_event("preview_ready", timeout_sec=cfg.timeout_sec)

    step_ms: list[float] = []
    for step in range(cfg.swipe_count):
        adb_util.clear_logcat()
        adb_util.tap_content_desc(exact="Next image")
        fields = adb_util.wait_for_bench_event(
            "preview_navigate", timeout_sec=cfg.timeout_sec
        )
        elapsed = float(fields.get("elapsed_ms", "nan"))
        step_ms.append(elapsed)
        _emit(
            rows,
            cfg,
            "swipe_preview",
            "step_duration_ms",
            "ms",
            iteration,
            elapsed,
        )

    if step_ms:
        _emit(
            rows,
            cfg,
            "swipe_preview",
            "mean_step_ms",
            "ms",
            iteration,
            statistics.fmean(step_ms),
        )


def run_scroll_gallery(cfg: BenchConfig, iteration: int, rows: list[dict]) -> None:
    ensure_gallery_ready(cfg, force_cold=True)
    width, height = adb_util.window_size()
    x = width // 2
    y1 = int(height * 0.75)
    y2 = int(height * 0.25)

    adb_util.gfxinfo_reset(cfg.package)
    time.sleep(0.2)
    for _ in range(cfg.scroll_flings):
        adb_util.input_swipe(x, y1, x, y2, duration_ms=350)
        time.sleep(0.35)

    # Allow outstanding frames to settle before dump.
    time.sleep(0.5)
    raw = adb_util.gfxinfo_framestats(cfg.package)
    durations = adb_util.parse_framestats(raw)

    if not durations:
        _emit(rows, cfg, "scroll_gallery", "frame_count", "count", iteration, 0.0)
        _emit(rows, cfg, "scroll_gallery", "jank_percent", "percent", iteration, 0.0)
        return

    janky = sum(1 for d in durations if d > JANK_THRESHOLD_MS)
    jank_percent = 100.0 * janky / len(durations)
    ordered = sorted(durations)
    p50 = statistics.median(ordered)
    # nearest-rank style p95
    p95_index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    p95 = ordered[p95_index]
    max_frame = ordered[-1]

    _emit(rows, cfg, "scroll_gallery", "frame_count", "count", iteration, float(len(durations)))
    _emit(rows, cfg, "scroll_gallery", "jank_percent", "percent", iteration, jank_percent)
    _emit(rows, cfg, "scroll_gallery", "percentile_50_ms", "ms", iteration, p50)
    _emit(rows, cfg, "scroll_gallery", "percentile_95_ms", "ms", iteration, p95)
    _emit(rows, cfg, "scroll_gallery", "max_frame_ms", "ms", iteration, max_frame)
    _emit(rows, cfg, "scroll_gallery", "mean_frame_ms", "ms", iteration, statistics.fmean(ordered))


def run_memory(cfg: BenchConfig, iteration: int, rows: list[dict]) -> None:
    ensure_gallery_ready(cfg, force_cold=True)
    time.sleep(0.8)
    text = adb_util.meminfo(cfg.package)
    parsed = adb_util.parse_meminfo(text)
    for metric, value in parsed.items():
        _emit(rows, cfg, "memory", metric, "kb", iteration, value)


SCENARIOS: dict[str, Callable[[BenchConfig, int, list[dict]], None]] = {
    "cold_startup": run_cold_startup,
    "open_preview": run_open_preview,
    "swipe_preview": run_swipe_preview,
    "scroll_gallery": run_scroll_gallery,
    "memory": run_memory,
}

ALL_SCENARIOS = list(SCENARIOS.keys())
