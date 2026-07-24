#!/usr/bin/env python3
"""
Generate the mixed (varied resolution/aspect) 300-image gallery dataset for CS426.

Enforces an approximate ARGB_8888 decoded-memory budget so Phase 1 eager decode
remains runnable. Deterministic offline generator; requires Pillow.
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
JPEG_QUALITY = 85
BYTES_PER_PIXEL_ARGB8888 = 4
# Safety budget for Phase 1 decoding all images at full size on a typical mid-range heap.
DEFAULT_DECODED_BUDGET_MIB = 180.0

# Aspect ratios: (name, width_ratio, height_ratio)
ASPECTS = (
    ("1:1", 1, 1),
    ("4:3", 4, 3),
    ("3:4", 3, 4),
    ("16:9", 16, 9),
    ("9:16", 9, 16),
)

# Long-edge buckets: majority low, fewer medium, limited high.
# Counts for 300: 210 low + 60 medium + 30 high.
LOW_COUNT = 210
MEDIUM_COUNT = 60
HIGH_COUNT = 30
LOW_LONG_EDGE = 192
MEDIUM_LONG_EDGE = 320
HIGH_LONG_EDGE = 480


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the mixed varied gallery dataset (300 images)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datasets/generated/mixed"),
        help="Output directory (will contain images/ and manifest.json)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Deterministic seed")
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help="Image count (default 300; do not change for seminar comparisons)",
    )
    parser.add_argument(
        "--budget-mib",
        type=float,
        default=DEFAULT_DECODED_BUDGET_MIB,
        help=f"Fail if estimated ARGB_8888 footprint exceeds this MiB (default {DEFAULT_DECODED_BUDGET_MIB})",
    )
    return parser.parse_args()


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


def size_for_index(index_zero: int) -> tuple[int, int, str, str]:
    """
    Return (width, height, tier, aspect_name) for 0-based index.
    Distribution: indices 0..209 low, 210..269 medium, 270..299 high.
    """
    if index_zero < LOW_COUNT:
        tier = "low"
        long_edge = LOW_LONG_EDGE
    elif index_zero < LOW_COUNT + MEDIUM_COUNT:
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


def make_image(index: int, width: int, height: int, seed: int, tier: str) -> Image.Image:
    hue = ((index * 41 + seed * 17) % 360) / 360.0
    top = hsv_to_rgb(hue, 0.5, 0.92)
    bottom = hsv_to_rgb((hue + 0.22) % 1.0, 0.7, 0.5)

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(int(top[c] * (1 - t) + bottom[c] * t) for c in range(3))
        draw.line([(0, y), (width - 1, y)], fill=color)

    # Soft diagonal stripes for texture without noise (keeps files small).
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


def prepare_output_dir(output: Path) -> Path:
    images_dir = output / "images"
    if output.exists():
        shutil.rmtree(output)
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def main() -> int:
    args = parse_args()
    if args.count != DEFAULT_COUNT:
        print(
            f"WARNING: seminar datasets normally use count={DEFAULT_COUNT}; "
            f"got {args.count}",
            file=sys.stderr,
        )
    if args.count <= 0:
        print("ERROR: --count must be positive", file=sys.stderr)
        return 1
    if LOW_COUNT + MEDIUM_COUNT + HIGH_COUNT != DEFAULT_COUNT:
        print("ERROR: internal tier counts must sum to 300", file=sys.stderr)
        return 1
    if args.count != DEFAULT_COUNT:
        print(
            "ERROR: mixed generator currently supports only count=300 "
            "(fixed low/medium/high tiers).",
            file=sys.stderr,
        )
        return 1

    # Pre-compute sizes and budget before writing files.
    specs = [size_for_index(i) for i in range(args.count)]
    decoded_bytes = sum(w * h * BYTES_PER_PIXEL_ARGB8888 for w, h, _, _ in specs)
    budget_bytes = args.budget_mib * 1024 * 1024
    if decoded_bytes > budget_bytes:
        print(
            f"ERROR: estimated decoded footprint "
            f"{decoded_bytes / (1024 * 1024):.2f} MiB exceeds budget "
            f"{args.budget_mib:.2f} MiB. Reduce long-edge buckets or raise --budget-mib.",
            file=sys.stderr,
        )
        return 1

    images_dir = prepare_output_dir(args.output)
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
        img = make_image(i, width, height, args.seed, tier)
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
        "dataset": "mixed",
        "seed": args.seed,
        "count": args.count,
        "format": "JPEG",
        "jpeg_quality": JPEG_QUALITY,
        "decoded_budget_mib": args.budget_mib,
        "estimated_decoded_mib": round(decoded_bytes / (1024 * 1024), 2),
        "resolution_distribution": {
            "low": {"count": LOW_COUNT, "long_edge": LOW_LONG_EDGE},
            "medium": {"count": MEDIUM_COUNT, "long_edge": MEDIUM_LONG_EDGE},
            "high": {"count": HIGH_COUNT, "long_edge": HIGH_LONG_EDGE},
        },
        "aspect_ratios": [a[0] for a in ASPECTS],
        "images": manifest_items,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("Mixed dataset generated")
    print(f"  output:          {args.output.resolve()}")
    print(f"  count:           {args.count}")
    print(f"  seed:            {args.seed}")
    print(f"  tiers:           low={tier_counts['low']} medium={tier_counts['medium']} high={tier_counts['high']}")
    print(f"  resolution:      {min_w}x{min_h} .. {max_w}x{max_h}")
    print(f"  aspects:         {', '.join(a[0] for a in ASPECTS)}")
    print(f"  encoded disk:    {encoded_bytes / (1024 * 1024):.2f} MiB")
    print(f"  est. decoded:    {decoded_bytes / (1024 * 1024):.2f} MiB (ARGB_8888)")
    print(f"  budget:          {args.budget_mib:.2f} MiB")
    print(f"  manifest:        {manifest_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
