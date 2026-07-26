#!/usr/bin/env python3
"""
Generate a CS426 gallery dataset (offline, deterministic).

Two built-in profiles:
  easy  — uniform square JPEGs
  mixed — varied resolution/aspect with a decoded-memory budget check

Requires Pillow (pip install Pillow).
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    print(
        "ERROR: Pillow is required. Install with: pip install Pillow",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

DEFAULT_COUNT = 300
DEFAULT_SEED = 2026
DEFAULT_EASY_SIZE = 256
JPEG_QUALITY = 85
BYTES_PER_PIXEL_ARGB8888 = 4
DEFAULT_DECODED_BUDGET_MIB = 180.0
DEFAULT_GENERATED_ROOT = Path("datasets/generated")

PROFILES = ("easy", "mixed")

# Aspect ratios: (name, width_ratio, height_ratio)
ASPECTS = (
    ("1:1", 1, 1),
    ("4:3", 4, 3),
    ("3:4", 3, 4),
    ("16:9", 16, 9),
    ("9:16", 9, 16),
)

# Long-edge buckets for mixed (canonical 300-image split: 210 / 60 / 30).
LOW_LONG_EDGE = 192
MEDIUM_LONG_EDGE = 320
HIGH_LONG_EDGE = 480
CANONICAL_LOW = 210
CANONICAL_MEDIUM = 60
CANONICAL_HIGH = 30


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an easy or mixed gallery dataset under datasets/generated/<name>/."
        ),
    )
    parser.add_argument(
        "--profile",
        "-p",
        choices=PROFILES,
        required=True,
        help="Generation recipe: easy (uniform squares) or mixed (varied res/aspect).",
    )
    parser.add_argument(
        "--name",
        "-n",
        default=None,
        help=(
            "Output folder name under --output-root (default: same as --profile). "
            "Also used as the Android assets dataset folder name when --sync is set."
        ),
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Image count (default {DEFAULT_COUNT}; keep 300 for seminar comparisons).",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=DEFAULT_SEED,
        help=f"Deterministic seed (default {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_GENERATED_ROOT,
        help=f"Parent directory for named datasets (default {DEFAULT_GENERATED_ROOT}).",
    )
    parser.add_argument(
        "--force-replace",
        "-f",
        action="store_true",
        help="Replace an existing output folder without prompting (default: ask / abort).",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="After generate, copy into app/src/main/assets/datasets/<name>/.",
    )
    parser.add_argument(
        "--assets-root",
        type=Path,
        default=Path("app/src/main/assets/datasets"),
        help="Android assets datasets root (used with --sync).",
    )
    # Profile-specific knobs
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_EASY_SIZE,
        help=f"easy only: square edge in pixels (default {DEFAULT_EASY_SIZE}).",
    )
    parser.add_argument(
        "--budget-mib",
        type=float,
        default=DEFAULT_DECODED_BUDGET_MIB,
        help=(
            f"mixed only: fail if estimated ARGB_8888 footprint exceeds this MiB "
            f"(default {DEFAULT_DECODED_BUDGET_MIB})."
        ),
    )
    return parser.parse_args(argv)


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i %= 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)


def mixed_tier_counts(count: int) -> tuple[int, int, int]:
    """Return (low, medium, high) counts that sum to count (~70/20/10)."""
    if count == DEFAULT_COUNT:
        return CANONICAL_LOW, CANONICAL_MEDIUM, CANONICAL_HIGH
    low = int(count * 0.70)
    medium = int(count * 0.20)
    high = count - low - medium
    if high < 0:
        medium = max(0, medium + high)
        high = 0
        if medium < 0:
            low = count
            medium = 0
    return low, medium, high


def size_for_index(
    index_zero: int,
    low_count: int,
    medium_count: int,
) -> tuple[int, int, str, str]:
    """Return (width, height, tier, aspect_name) for a 0-based index."""
    if index_zero < low_count:
        tier = "low"
        long_edge = LOW_LONG_EDGE
    elif index_zero < low_count + medium_count:
        tier = "medium"
        long_edge = MEDIUM_LONG_EDGE
    else:
        tier = "high"
        long_edge = HIGH_LONG_EDGE

    aspect_name, wr, hr = ASPECTS[index_zero % len(ASPECTS)]
    if wr >= hr:
        width = long_edge
        height = max(1, round(long_edge * hr / wr))
    else:
        height = long_edge
        width = max(1, round(long_edge * wr / hr))
    return width, height, tier, aspect_name


def make_easy_image(index: int, size: int, seed: int) -> Image.Image:
    hue = ((index * 37 + seed * 13) % 360) / 360.0
    top = hsv_to_rgb(hue, 0.55, 0.95)
    bottom = hsv_to_rgb((hue + 0.18) % 1.0, 0.65, 0.55)

    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(size - 1, 1)
        color = tuple(int(top[c] * (1 - t) + bottom[c] * t) for c in range(3))
        draw.line([(0, y), (size - 1, y)], fill=color)

    margin = size // 8
    shape = index % 3
    accent = hsv_to_rgb((hue + 0.42) % 1.0, 0.8, 0.9)
    if shape == 0:
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            outline=accent,
            width=max(2, size // 64),
        )
    elif shape == 1:
        draw.rectangle(
            [margin, margin, size - margin, size - margin],
            outline=accent,
            width=max(2, size // 64),
        )
    else:
        cx, cy = size // 2, size // 2
        r = size // 2 - margin
        points = [
            (
                cx + int(r * math.cos(math.radians(a))),
                cy + int(r * math.sin(math.radians(a))),
            )
            for a in (270, 30, 150)
        ]
        draw.polygon(points, outline=accent)

    label = f"{index:04d}"
    font = ImageFont.load_default()
    try:
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(label, font=font)
    tx = (size - tw) // 2
    ty = (size - th) // 2
    draw.text((tx + 1, ty + 1), label, fill=(0, 0, 0), font=font)
    draw.text((tx, ty), label, fill=(255, 255, 255), font=font)
    return img


def make_mixed_image(
    index: int, width: int, height: int, seed: int, tier: str
) -> Image.Image:
    hue = ((index * 41 + seed * 17) % 360) / 360.0
    top = hsv_to_rgb(hue, 0.5, 0.92)
    bottom = hsv_to_rgb((hue + 0.22) % 1.0, 0.7, 0.5)

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(int(top[c] * (1 - t) + bottom[c] * t) for c in range(3))
        draw.line([(0, y), (width - 1, y)], fill=color)

    stripe = hsv_to_rgb((hue + 0.08) % 1.0, 0.35, 0.85)
    step = max(8, min(width, height) // 12)
    for offset in range(-height, width, step):
        draw.line([(offset, 0), (offset + height, height)], fill=stripe, width=1)

    margin_x = max(4, width // 10)
    margin_y = max(4, height // 10)
    accent = hsv_to_rgb((hue + 0.45) % 1.0, 0.85, 0.95)
    shape = index % 4
    if shape == 0:
        draw.ellipse(
            [margin_x, margin_y, width - margin_x, height - margin_y],
            outline=accent,
            width=max(2, min(width, height) // 48),
        )
    elif shape == 1:
        draw.rectangle(
            [margin_x, margin_y, width - margin_x, height - margin_y],
            outline=accent,
            width=max(2, min(width, height) // 48),
        )
    elif shape == 2:
        cx, cy = width // 2, height // 2
        r = min(width, height) // 2 - min(margin_x, margin_y)
        points = [
            (
                cx + int(r * math.cos(math.radians(a))),
                cy + int(r * math.sin(math.radians(a))),
            )
            for a in (270, 30, 150)
        ]
        draw.polygon(points, outline=accent)
    else:
        draw.line(
            [(margin_x, margin_y), (width - margin_x, height - margin_y)],
            fill=accent,
            width=max(2, min(width, height) // 48),
        )
        draw.line(
            [(width - margin_x, margin_y), (margin_x, height - margin_y)],
            fill=accent,
            width=max(2, min(width, height) // 48),
        )

    label = f"{index:04d}\n{tier}\n{width}x{height}"
    font = ImageFont.load_default()
    try:
        bbox = draw.multiline_textbbox((0, 0), label, font=font, align="center")
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.multiline_textsize(label, font=font)
    tx = (width - tw) // 2
    ty = (height - th) // 2
    draw.multiline_text((tx + 1, ty + 1), label, fill=(0, 0, 0), font=font, align="center")
    draw.multiline_text((tx, ty), label, fill=(255, 255, 255), font=font, align="center")
    return img


def confirm_replace(output: Path, force_replace: bool) -> bool:
    """Return True if generation may proceed (folder cleared or absent)."""
    if not output.exists():
        return True
    if force_replace:
        print(f"Replacing existing dataset folder: {output}")
        return True
    if not sys.stdin.isatty():
        print(
            f"ERROR: output already exists: {output}\n"
            f"Remove it first, or re-run with --force-replace.",
            file=sys.stderr,
        )
        return False
    answer = input(
        f"Output folder already exists: {output}\n"
        f"Replace it? [y/N]: "
    ).strip().lower()
    if answer in ("y", "yes"):
        return True
    print(
        "Aborted. Remove the folder manually or pass --force-replace.",
        file=sys.stderr,
    )
    return False


def prepare_output_dir(output: Path) -> Path:
    images_dir = output / "images"
    if output.exists():
        shutil.rmtree(output)
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def sync_to_assets(src: Path, dest: Path) -> None:
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


def generate_easy(args: argparse.Namespace, output: Path) -> int:
    if args.size < 16:
        print("ERROR: --size must be at least 16", file=sys.stderr)
        return 1

    images_dir = prepare_output_dir(output)
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    manifest_items = []
    encoded_bytes = 0

    for i in range(1, args.count + 1):
        filename = f"image_{i:04d}.jpg"
        path = images_dir / filename
        img = make_easy_image(i, args.size, args.seed)
        img.save(path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        encoded_bytes += path.stat().st_size
        timestamp = (base_time + timedelta(seconds=i - 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest_items.append(
            {
                "id": i,
                "filename": filename,
                "timestamp": timestamp,
                "width": args.size,
                "height": args.size,
            }
        )

    manifest = {
        "dataset": args.name,
        "profile": "easy",
        "seed": args.seed,
        "count": args.count,
        "format": "JPEG",
        "jpeg_quality": JPEG_QUALITY,
        "resolution": {"width": args.size, "height": args.size},
        "images": manifest_items,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    decoded_bytes = args.count * args.size * args.size * BYTES_PER_PIXEL_ARGB8888
    print("Easy dataset generated")
    print(f"  name:            {args.name}")
    print(f"  output:          {output.resolve()}")
    print(f"  count:           {args.count}")
    print(f"  seed:            {args.seed}")
    print(f"  resolution:      {args.size}x{args.size} (square)")
    print(f"  encoded disk:    {encoded_bytes / (1024 * 1024):.2f} MiB")
    print(f"  est. decoded:    {decoded_bytes / (1024 * 1024):.2f} MiB (ARGB_8888)")
    print(f"  manifest:        {manifest_path.name}")
    return 0


def generate_mixed(args: argparse.Namespace, output: Path) -> int:
    if args.count != DEFAULT_COUNT:
        print(
            f"WARNING: seminar datasets normally use count={DEFAULT_COUNT}; "
            f"got {args.count} (tiers scaled ~70/20/10).",
            file=sys.stderr,
        )

    low_count, medium_count, high_count = mixed_tier_counts(args.count)
    if low_count + medium_count + high_count != args.count:
        print("ERROR: internal tier counts do not sum to --count", file=sys.stderr)
        return 1

    specs = [
        size_for_index(i, low_count, medium_count) for i in range(args.count)
    ]
    decoded_bytes = sum(w * h * BYTES_PER_PIXEL_ARGB8888 for w, h, _, _ in specs)
    budget_bytes = args.budget_mib * 1024 * 1024
    if decoded_bytes > budget_bytes:
        print(
            f"ERROR: estimated decoded footprint "
            f"{decoded_bytes / (1024 * 1024):.2f} MiB exceeds budget "
            f"{args.budget_mib:.2f} MiB. Reduce --count / long-edge buckets "
            f"or raise --budget-mib.",
            file=sys.stderr,
        )
        return 1

    images_dir = prepare_output_dir(output)
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    manifest_items = []
    encoded_bytes = 0
    min_w = min_h = 10**9
    max_w = max_h = 0
    tier_counts = {"low": 0, "medium": 0, "high": 0}

    for i in range(1, args.count + 1):
        width, height, tier, aspect_name = specs[i - 1]
        filename = f"image_{i:04d}.jpg"
        path = images_dir / filename
        img = make_mixed_image(i, width, height, args.seed, tier)
        img.save(path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        encoded_bytes += path.stat().st_size
        timestamp = (base_time + timedelta(seconds=i - 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest_items.append(
            {
                "id": i,
                "filename": filename,
                "timestamp": timestamp,
                "width": width,
                "height": height,
                "tier": tier,
                "aspect": aspect_name,
            }
        )
        min_w, max_w = min(min_w, width), max(max_w, width)
        min_h, max_h = min(min_h, height), max(max_h, height)
        tier_counts[tier] += 1

    manifest = {
        "dataset": args.name,
        "profile": "mixed",
        "seed": args.seed,
        "count": args.count,
        "format": "JPEG",
        "jpeg_quality": JPEG_QUALITY,
        "decoded_budget_mib": args.budget_mib,
        "estimated_decoded_mib": round(decoded_bytes / (1024 * 1024), 2),
        "resolution_distribution": {
            "low": {"count": low_count, "long_edge": LOW_LONG_EDGE},
            "medium": {"count": medium_count, "long_edge": MEDIUM_LONG_EDGE},
            "high": {"count": high_count, "long_edge": HIGH_LONG_EDGE},
        },
        "aspect_ratios": [a[0] for a in ASPECTS],
        "images": manifest_items,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("Mixed dataset generated")
    print(f"  name:            {args.name}")
    print(f"  output:          {output.resolve()}")
    print(f"  count:           {args.count}")
    print(f"  seed:            {args.seed}")
    print(
        f"  tiers:           low={tier_counts['low']} "
        f"medium={tier_counts['medium']} high={tier_counts['high']}"
    )
    print(f"  resolution:      {min_w}x{min_h} .. {max_w}x{max_h}")
    print(f"  aspects:         {', '.join(a[0] for a in ASPECTS)}")
    print(f"  encoded disk:    {encoded_bytes / (1024 * 1024):.2f} MiB")
    print(f"  est. decoded:    {decoded_bytes / (1024 * 1024):.2f} MiB (ARGB_8888)")
    print(f"  budget:          {args.budget_mib:.2f} MiB")
    print(f"  manifest:        {manifest_path.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.count <= 0:
        print("ERROR: --count must be positive", file=sys.stderr)
        return 1

    name = args.name or args.profile
    if not name or any(ch in name for ch in ("/", "\\", "..")):
        print("ERROR: --name must be a simple folder name (no path separators).", file=sys.stderr)
        return 1
    args.name = name

    output = args.output_root / name
    if not confirm_replace(output, args.force_replace):
        return 1

    if args.profile == "easy":
        code = generate_easy(args, output)
    else:
        code = generate_mixed(args, output)
    if code != 0:
        return code

    if args.sync:
        try:
            sync_to_assets(output, args.assets_root / name)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
