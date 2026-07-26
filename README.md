# CS426 Android Image Gallery (Seminar)

Educational Android gallery used to study **viewport-based view creation and image loading** versus eagerly building and decoding the entire gallery.

## Research question

How much does viewport-based view creation and image loading improve scrolling smoothness in a Java Android image gallery compared with eagerly creating the entire gallery and decoding all images in advance?

Benchmarking is performed by the student group after both phases exist. This repository does not ship fabricated performance numbers.

## Stack

- Java
- Android Views + XML
- Gradle Groovy (`build.gradle`)
- AndroidX AppCompat / Material

## Requirements

- Android Studio (recent stable) with Android SDK Platform **35**
- JDK **17** (project `compileOptions` target 17; newer JDKs may work for the Gradle daemon if configured)
- Python **3** + [Pillow](https://pillow.readthedocs.io/) (`pip install Pillow`) for dataset scripts
- No network required at app runtime

## Project layout (current)

See `PROJECT_CONTEXT.md` for the live map. High level:

```text
app/                 Android module (gallery + preview)
tools/datasets/      Dataset generators + asset sync
tools/benchmark/     Automated adb benchmark CLI → CSV
datasets/generated/  Script output
docs/benchmark/      Benchmark CSV output (contents gitignored)
```

Package: `com.cs426.gallery`

## Build and run

1. Open the project root in Android Studio.
2. Set SDK path in `local.properties` (`sdk.dir=...`) if Studio does not create it.
3. Generate datasets and sync into assets (see below) if `app/src/main/assets/datasets/*/images/` is missing.
4. Sync Gradle and run the `app` configuration on a device/emulator (API 24+).

Command line (after wrapper + SDK are available):

```bash
./gradlew :app:assembleDebug
./gradlew :app:assembleDebug -PgalleryDataset=easy
./gradlew :app:assembleDebug -PgalleryDataset=mixed
```

Default dataset property: **`mixed`** (`gradle.properties` → `galleryDataset=mixed` → `BuildConfig.GALLERY_DATASET`).

## Datasets

Two offline **300-image** JPEG datasets (seed **2026**):

| Name | Purpose | Notes |
|------|---------|-------|
| `easy` | Uniform square images | 256×256; ~75 MiB estimated ARGB_8888 if all decoded |
| `mixed` | Varied resolution/aspect | 210 low / 60 medium / 30 high long-edge; aspects 1:1, 4:3, 3:4, 16:9, 9:16; fails if decoded estimate exceeds **180 MiB** budget (~57.5 MiB with defaults) |

Manifest fields: `id`, `filename`, `timestamp`, `width`, `height` (mixed also records `tier` / `aspect`). Order: oldest → newest by timestamp then id.

### Generate

From the project root:

```bash
python tools/datasets/generate_easy_dataset.py --output datasets/generated/easy --seed 2026
python tools/datasets/generate_mixed_dataset.py --output datasets/generated/mixed --seed 2026
python tools/datasets/sync_datasets_to_assets.py
```

Asset layout after sync:

```text
app/src/main/assets/datasets/{easy|mixed}/
├── images/
│   ├── image_0001.jpg
│   └── ...
└── manifest.json
```

**Commit policy:** generated image binaries are gitignored; regenerate with scripts, then sync into assets before building. Manifests under `datasets/generated/` may be committed for checksum verification.

## Git tags

| Tag | Meaning |
|-----|---------|
| `v1-unoptimized` | Eager baseline (tagged; emulator-verified) |
| `v2-step-1-recyclerview` | RecyclerView grid (tagged) |
| `v2-step-2-viewport-loading` | Bind-time load (tagged; primary) |
| `v2-step-3-background-decoding` | Bounded executor (tagged) |
| `v2-step-4-sized-thumbnails` | Display-sized decode (tagged) |
| `v2-step-5-bounded-cache` | Bounded `LruCache` (tagged) |
| `v2-step-6-scroll-aware-prefetch` | Defer UI bitmap apply while flinging + off-screen cache prefetch (tagged) |
| `v2-optimized` | Final verified state (planned) |

Current tag: **`v2-step-6-scroll-aware-prefetch`** — while dragging/settling, skip main-thread `setImageBitmap` for decode completions (cache still fills); prefetch ~2 rows into the bounded thumbnail cache; larger RecyclerView item cache.

## How to benchmark

Automated host-side harness under `tools/benchmark/` (Python **3.9+**, **stdlib only** — no pip packages). It drives the app over **adb**, reads on-device `GalleryBench` log markers (wall-clock latency) plus `dumpsys gfxinfo` / `meminfo` (scroll frames / memory), then writes CSV.

Measurements use in-app `SystemClock` markers and system frame dumps, so the Python driver does not sit on the app’s UI thread. Occasional one-line logs have negligible cost compared with image decode.

### Prerequisites

1. Unlocked emulator or device with USB debugging (`adb devices` shows `device`).
2. App installed for the dataset you intend to measure (or pass `--install`).
3. `adb` on `PATH` (Android SDK platform-tools).

### Run

From the project root:

```bash
# Device connected; app already installed (mixed dataset build)
python tools/benchmark/run_benchmark.py --tag v1-unoptimized --iterations 10

# Rebuild/install easy dataset, then run a subset
python tools/benchmark/run_benchmark.py --install --dataset easy --scenarios cold_startup,scroll_gallery --iterations 5 --tag v1-easy

# Customize warmup, swipe steps, scroll flings, output location
python tools/benchmark/run_benchmark.py --tag v2-optimized --warmup 2 --iterations 15 --swipe-count 8 --scroll-flings 12 --output-dir docs/benchmark
```

On Windows, use the same commands; `--install` invokes `gradlew.bat` when present.

### Useful flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--iterations` | `10` | Measured runs per scenario |
| `--warmup` | `1` | Discarded runs before measurement |
| `--scenarios` | all five | Comma list: `cold_startup,open_preview,swipe_preview,scroll_gallery,memory` |
| `--dataset` | `mixed` | CSV label; with `--install`, passed as `-PgalleryDataset=` |
| `--install` | off | `installDebug` before the suite |
| `--tag` | `untagged` | Label column in CSV (e.g. git tag name) |
| `--preview-index` | `0` | Zero-based cell to open (id ≈ index+1) |
| `--swipe-count` | `5` | Next-arrow steps per `swipe_preview` run |
| `--scroll-flings` | `8` | Swipes per `scroll_gallery` run |
| `--timeout-sec` | `180` | Wait budget for Phase 1 cold start |
| `--output-dir` | `docs/benchmark/` | CSV directory |
| `--output-prefix` | `<tag>_<dataset>_<utc>` | Filename prefix |

### Scenarios

| Scenario | What it measures |
|----------|------------------|
| `cold_startup` | Force-stop → launch → `gallery_ready` (`elapsed_ms`, includes Phase 1 decode-all + eager grid) |
| `open_preview` | Tap gallery cell → `preview_ready` |
| `swipe_preview` | Repeated **Next** taps → `preview_navigate` step times |
| `scroll_gallery` | Fixed swipes + `gfxinfo framestats` → jank %, frame percentiles (primary UX metric) |
| `memory` | `dumpsys meminfo` after gallery ready — **supporting** evidence only |

### Output

Each run writes two files (contents of `docs/benchmark/` are gitignored):

- `{prefix}_runs.csv` — every sample: tag, dataset, scenario, metric, unit, iteration, value, timestamp
- `{prefix}_summary.csv` — per scenario+metric: **n, mean, median, stdev, min, max, p95**

Optional deep dives (not automated here): Perfetto / System Trace, Android Studio Memory Profiler.

## Known limitations

- Phase 1 is memory- and main-thread-heavy by design (eager views + decode-all-at-init); datasets stay within a runnable decoded-memory budget (mixed generator enforces `--budget-mib`, default 180).
- First launch may hitch while all images decode on the main thread — intentional baseline behavior, not a fake delay.
- Android SDK may need `sdk.dir` in `local.properties` for command-line builds.
