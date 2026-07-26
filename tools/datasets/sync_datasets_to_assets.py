#!/usr/bin/env python3
"""Copy generated datasets into app/src/main/assets/datasets/<name>/."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def sync_one(src: Path, dest: Path) -> None:
    if not (src / "manifest.json").is_file():
        raise FileNotFoundError(f"Missing manifest: {src / 'manifest.json'}")
    if not (src / "images").is_dir():
        raise FileNotFoundError(f"Missing images dir: {src / 'images'}")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "manifest.json", dest / "manifest.json")
    shutil.copytree(src / "images", dest / "images")
    image_count = len(list((dest / "images").glob("*.jpg")))
    print(f"Synced {src} -> {dest} ({image_count} jpg + manifest)")


def discover_names(generated_root: Path) -> list[str]:
    if not generated_root.is_dir():
        return []
    names: list[str] = []
    for child in sorted(generated_root.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            names.append(child.name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync generated datasets into Android assets.",
    )
    parser.add_argument(
        "--generated-root",
        type=Path,
        default=Path("datasets/generated"),
        help="Root containing named dataset folders",
    )
    parser.add_argument(
        "--assets-root",
        type=Path,
        default=Path("app/src/main/assets/datasets"),
        help="Android assets datasets root",
    )
    parser.add_argument(
        "--dataset",
        "-d",
        default="all",
        help=(
            "Dataset folder name to sync, or 'all' for every folder under "
            "--generated-root that has a manifest.json (default: all)."
        ),
    )
    args = parser.parse_args()

    if args.dataset == "all":
        names = discover_names(args.generated_root)
        if not names:
            print(
                f"ERROR: no datasets with manifest.json under {args.generated_root}",
                file=sys.stderr,
            )
            return 1
    else:
        names = [args.dataset]

    try:
        for name in names:
            sync_one(args.generated_root / name, args.assets_root / name)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
