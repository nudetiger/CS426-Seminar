#!/usr/bin/env python3
"""
Automated gallery benchmark runner (host-side).

Drives the installed CS426 gallery app over adb, reads GalleryBench log markers and
dumpsys metrics, then writes per-run and summary CSV files.

Supports a single labeled run (--tag) or a multi-version sweep (--versions) that
checks out each git ref in a temporary worktree, installs that APK, then measures
with this tip-of-tree harness (so older tags still get the current runner).

Requires: Python 3.9+, adb on PATH, unlocked device/emulator.
Stdlib only — no pip packages required.
"""

from __future__ import annotations

import argparse
import os
import shutil
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
WORKTREE_ROOT = REPO_ROOT / ".bench-worktrees"

ADB_PATH_HINT = (
    "adb not found on PATH. Install Android SDK platform-tools, then add it to PATH.\n"
    "  PowerShell (session):  $env:Path += \";C:\\Users\\Admin\\AppData\\Local\\Android\\Sdk\\platform-tools\"\n"
    "  bash:                  export PATH=\"$PATH:$HOME/Library/Android/sdk/platform-tools\"  # macOS example"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run automated CS426 gallery benchmarks and export CSV results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Multi-version example:\n"
            "  python tools/benchmark/run_benchmark.py "
            "--versions v1-unoptimized,v2-optimized "
            "--dataset mixed --iterations 10 --output-dir docs/benchmark\n"
            "\n"
            "If adb is missing from PATH (Windows PowerShell):\n"
            "  $env:Path += \";C:\\Users\\Admin\\AppData\\Local\\Android\\Sdk\\platform-tools\""
        ),
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
        default="mixed",
        help=(
            "Dataset folder name / CSV label (default: mixed). "
            "With install, passed as -PgalleryDataset=<dataset>."
        ),
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
        help="Label written into CSV rows for a single-version run (e.g. v1-unoptimized).",
    )
    parser.add_argument(
        "--versions",
        default=None,
        help=(
            "Comma-separated git refs/tags to measure in one CLI "
            "(e.g. v1-unoptimized,v2-optimized). Implies install via temporary "
            "worktrees; CSV --tag is set to each ref. Incompatible with --tag "
            "unless --tag is left at default 'untagged'."
        ),
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
        help="Filename prefix for CSVs (default: <tag>_<dataset>_<timestamp>). "
        "Ignored when --versions lists more than one ref.",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="With --versions, continue after a version fails (default: stop on first failure).",
    )
    return parser.parse_args(argv)


def gradlew_cmd(project_root: Path) -> list[str]:
    if os.name == "nt":
        script = project_root / "gradlew.bat"
        if script.exists():
            return [str(script)]
    script = project_root / "gradlew"
    if script.exists():
        if os.name == "nt":
            return ["cmd", "/c", str(script)]
        return [str(script)]
    return ["gradle"]


def install_app(dataset: str, project_root: Path = REPO_ROOT) -> None:
    cmd = [
        *gradlew_cmd(project_root),
        ":app:installDebug",
        f"-PgalleryDataset={dataset}",
    ]
    print(f"Installing app: {' '.join(cmd)} (cwd={project_root})")
    completed = subprocess.run(cmd, cwd=str(project_root), check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Gradle installDebug failed with exit {completed.returncode}")


def resolve_scenarios(raw: str) -> list[str]:
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise ValueError("No scenarios selected")
    unknown = [name for name in names if name not in SCENARIOS]
    if unknown:
        raise ValueError(
            f"Unknown scenario(s): {', '.join(unknown)}. "
            f"Valid: {', '.join(ALL_SCENARIOS)}"
        )
    return names


def parse_versions(raw: str) -> list[str]:
    versions = [part.strip() for part in raw.split(",") if part.strip()]
    if not versions:
        raise ValueError("--versions is empty")
    return versions


def default_prefix(tag: str, dataset: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tag = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tag)
    return f"{safe_tag}_{dataset}_{stamp}"


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise SystemExit(f"git {' '.join(args)} failed: {detail}")
    return completed


def require_git_ref(ref: str) -> None:
    completed = run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"], check=False)
    if completed.returncode != 0:
        raise SystemExit(
            f"Unknown git ref '{ref}'. Create/fetch the tag first "
            f"(e.g. git tag -l 'v*')."
        )


def safe_worktree_name(ref: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in ref)


def resolve_dataset_source(dataset: str) -> Path:
    """Prefer tip assets (with images), else datasets/generated/<dataset>."""
    candidates = [
        REPO_ROOT / "app" / "src" / "main" / "assets" / "datasets" / dataset,
        REPO_ROOT / "datasets" / "generated" / dataset,
    ]
    for path in candidates:
        images = path / "images"
        if (path / "manifest.json").is_file() and images.is_dir():
            if any(images.glob("*.jpg")):
                return path
    raise SystemExit(
        f"Dataset '{dataset}' not found with images under "
        f"app/src/main/assets/datasets/{dataset} or datasets/generated/{dataset}.\n"
        f"Generate first, e.g.:\n"
        f"  python tools/datasets/generate_dataset.py --profile {dataset} "
        f"--force-replace --sync"
    )


def sync_dataset_into(project_root: Path, dataset: str, source: Path) -> None:
    dest = project_root / "app" / "src" / "main" / "assets" / "datasets" / dataset
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "manifest.json", dest / "manifest.json")
    shutil.copytree(source / "images", dest / "images")
    count = len(list((dest / "images").glob("*.jpg")))
    print(f"Synced dataset '{dataset}' -> {dest} ({count} jpg)")


def ensure_local_properties(project_root: Path) -> None:
    tip = REPO_ROOT / "local.properties"
    dest = project_root / "local.properties"
    if tip.is_file() and project_root.resolve() != REPO_ROOT.resolve():
        shutil.copy2(tip, dest)


def remove_worktree(path: Path) -> None:
    if not path.exists():
        return
    run_git(["worktree", "remove", "--force", str(path)], check=False)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    run_git(["worktree", "prune"], check=False)


def prepare_version_worktree(ref: str, dataset: str, source: Path) -> Path:
    require_git_ref(ref)
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORKTREE_ROOT / safe_worktree_name(ref)
    remove_worktree(path)
    print(f"\n--- Version {ref}: creating worktree at {path} ---")
    run_git(["worktree", "add", "--detach", str(path), ref])
    ensure_local_properties(path)
    sync_dataset_into(path, dataset, source)
    return path


def run_suite(
    *,
    tag: str,
    dataset: str,
    package: str,
    scenarios: list[str],
    warmup: int,
    iterations: int,
    timeout_sec: float,
    preview_index: int,
    swipe_count: int,
    scroll_flings: int,
    output_dir: Path,
    output_prefix: str | None,
) -> tuple[Path, Path]:
    cfg = BenchConfig(
        package=package,
        tag=tag,
        dataset=dataset,
        timeout_sec=timeout_sec,
        preview_index=preview_index,
        swipe_count=swipe_count,
        scroll_flings=scroll_flings,
    )

    prefix = output_prefix or default_prefix(tag, dataset)
    runs_path = output_dir / f"{prefix}_runs.csv"
    summary_path = output_dir / f"{prefix}_summary.csv"

    rows: list[dict] = []
    total_iters = warmup + iterations

    print(
        f"Benchmark tag={cfg.tag} dataset={cfg.dataset} "
        f"scenarios={scenarios} warmup={warmup} iterations={iterations}"
    )

    for scenario in scenarios:
        runner = SCENARIOS[scenario]
        print(f"\n=== Scenario: {scenario} ===")
        for i in range(total_iters):
            is_warmup = i < warmup
            measured_iteration = -1 if is_warmup else (i - warmup)
            label = "warmup" if is_warmup else f"iter {measured_iteration + 1}/{iterations}"
            print(f"  [{label}] running…", flush=True)
            try:
                if is_warmup:
                    discard: list[dict] = []
                    runner(cfg, -1, discard)
                else:
                    runner(cfg, measured_iteration, rows)
            except adb_util.AdbError as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)
                continue
            time.sleep(0.25)

    if not rows:
        raise RuntimeError("No samples collected; check device logs and app install.")

    output_dir.mkdir(parents=True, exist_ok=True)
    write_runs_csv(runs_path, rows)
    write_summary_csv(summary_path, rows, tag=cfg.tag, dataset=cfg.dataset)

    print(f"\nWrote {len(rows)} samples:")
    print(f"  {runs_path}")
    print(f"  {summary_path}")
    return runs_path, summary_path


def run_multi_versions(args: argparse.Namespace, scenarios: list[str]) -> int:
    versions = parse_versions(args.versions)
    for ref in versions:
        require_git_ref(ref)

    source = resolve_dataset_source(args.dataset)
    print(f"Using dataset source: {source}")

    failures: list[str] = []
    written: list[str] = []

    for ref in versions:
        worktree: Path | None = None
        try:
            worktree = prepare_version_worktree(ref, args.dataset, source)
            install_app(args.dataset, project_root=worktree)
            runs_path, summary_path = run_suite(
                tag=ref,
                dataset=args.dataset,
                package=args.package,
                scenarios=scenarios,
                warmup=args.warmup,
                iterations=args.iterations,
                timeout_sec=args.timeout_sec,
                preview_index=args.preview_index,
                swipe_count=args.swipe_count,
                scroll_flings=args.scroll_flings,
                output_dir=args.output_dir,
                output_prefix=None if len(versions) > 1 else args.output_prefix,
            )
            written.append(f"{runs_path.name}, {summary_path.name}")
        except (RuntimeError, ValueError, SystemExit) as exc:
            msg = str(exc) or "failed"
            print(f"ERROR: version {ref}: {msg}", file=sys.stderr)
            failures.append(ref)
            if not args.keep_going:
                if worktree is not None:
                    print(f"Cleaning worktree {worktree}")
                    remove_worktree(worktree)
                    worktree = None
                return 1
        finally:
            if worktree is not None:
                print(f"Cleaning worktree {worktree}")
                remove_worktree(worktree)

    if failures:
        print(
            f"\nCompleted with failures: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1

    print(f"\nMulti-version benchmark finished ({len(versions)} version(s)).")
    for line in written:
        print(f"  {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.iterations < 1:
        raise SystemExit("--iterations must be >= 1")
    if args.warmup < 0:
        raise SystemExit("--warmup must be >= 0")
    if not args.dataset or any(ch in args.dataset for ch in ("/", "\\", "..")):
        raise SystemExit("--dataset must be a simple folder name (no path separators)")

    if args.versions and args.tag != "untagged":
        raise SystemExit("Use either --versions or --tag, not both")

    try:
        scenarios = resolve_scenarios(args.scenarios)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        adb_util.require_device()
    except adb_util.AdbError as exc:
        text = str(exc)
        if "adb not found" in text.lower() or "not found on path" in text.lower():
            raise SystemExit(ADB_PATH_HINT) from exc
        raise SystemExit(text) from exc

    if args.versions:
        try:
            return run_multi_versions(args, scenarios)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

    if args.install:
        try:
            install_app(args.dataset, project_root=REPO_ROOT)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

    try:
        run_suite(
            tag=args.tag,
            dataset=args.dataset,
            package=args.package,
            scenarios=scenarios,
            warmup=args.warmup,
            iterations=args.iterations,
            timeout_sec=args.timeout_sec,
            preview_index=args.preview_index,
            swipe_count=args.swipe_count,
            scroll_flings=args.scroll_flings,
            output_dir=args.output_dir,
            output_prefix=args.output_prefix,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
