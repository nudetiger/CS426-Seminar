#!/usr/bin/env python3
"""
Generate the easy (uniform) 300-image gallery dataset for CS426.

Deterministic offline generator: same seed → same files and manifest.
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
DEFAULT_SIZE = 256
JPEG_QUALITY = 85
BYTES_PER_PIXEL_ARGB8888 = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the easy uniform square gallery dataset (300 images)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datasets/generated/easy"),
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
        "--size",
        type=int,
        default=DEFAULT_SIZE,
        help=f"Square edge in pixels (default {DEFAULT_SIZE})",
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


def make_image(index: int, size: int, seed: int) -> Image.Image:
    """Create a distinguishable square image from index + seed (no random noise)."""
    # Mix seed into color so regenerations with a different seed look different.
    hue = ((index * 37 + seed * 13) % 360) / 360.0
    top = hsv_to_rgb(hue, 0.55, 0.95)
    bottom = hsv_to_rgb((hue + 0.18) % 1.0, 0.65, 0.55)

    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(size - 1, 1)
        color = tuple(int(top[c] * (1 - t) + bottom[c] * t) for c in range(3))
        draw.line([(0, y), (size - 1, y)], fill=color)

    # Geometric accent shapes (deterministic from index).
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
    # Pillow 10+ uses textbbox; fall back for older versions.
    try:
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(label, font=font)
    tx = (size - tw) // 2
    ty = (size - th) // 2
    # Shadow for readability on varied gradients.
    draw.text((tx + 1, ty + 1), label, fill=(0, 0, 0), font=font)
    draw.text((tx, ty), label, fill=(255, 255, 255), font=font)
    return img


def prepare_output_dir(output: Path) -> Path:
    images_dir = output / "images"
    if output.exists():
        shutil.rmtree(output)
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def main() -> int:
    args = parse_args()
    if args.count <= 0:
        print("ERROR: --count must be positive", file=sys.stderr)
        return 1
    if args.size < 16:
        print("ERROR: --size must be at least 16", file=sys.stderr)
        return 1

    images_dir = prepare_output_dir(args.output)
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    manifest_items = []
    encoded_bytes = 0

    for i in range(1, args.count + 1):
        filename = f"image_{i:04d}.jpg"
        path = images_dir / filename
        img = make_image(i, args.size, args.seed)
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
        "dataset": "easy",
        "seed": args.seed,
        "count": args.count,
        "format": "JPEG",
        "jpeg_quality": JPEG_QUALITY,
        "resolution": {"width": args.size, "height": args.size},
        "images": manifest_items,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    decoded_bytes = args.count * args.size * args.size * BYTES_PER_PIXEL_ARGB8888
    print("Easy dataset generated")
    print(f"  output:          {args.output.resolve()}")
    print(f"  count:           {args.count}")
    print(f"  seed:            {args.seed}")
    print(f"  resolution:      {args.size}x{args.size} (square)")
    print(f"  encoded disk:    {encoded_bytes / (1024 * 1024):.2f} MiB")
    print(f"  est. decoded:    {decoded_bytes / (1024 * 1024):.2f} MiB (ARGB_8888)")
    print(f"  manifest:        {manifest_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
