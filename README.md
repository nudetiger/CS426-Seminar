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
datasets/generated/  Script output
docs/benchmark/      Group measurement outputs later
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

## Git tags (planned)

| Tag | Meaning |
|-----|---------|
| `v1-unoptimized` | Eager baseline |
| `v2-step-1-recyclerview` | RecyclerView grid |
| `v2-step-2-viewport-loading` | Bind-time load (primary) |
| `v2-step-3-background-decoding` | Bounded executor |
| `v2-step-4-sized-thumbnails` | Display-sized decode |
| `v2-step-5-bounded-cache` | Bounded `LruCache` |
| `v2-optimized` | Final verified state |

Current work is Phase 1 **functional baseline** (eager gallery + preview). Smoke-test, then tag `v1-unoptimized`.

## Planned benchmark tools (group)

- Jetpack Macrobenchmark + `FrameTimingMetric`
- Perfetto / System Trace
- Memory Profiler (supporting)
- Optional LeakCanary in debug

Store curated outputs under `docs/benchmark/`.

## Known limitations

- Phase 1 is memory- and main-thread-heavy by design (eager views + decode-all-at-init); datasets stay within a runnable decoded-memory budget (mixed generator enforces `--budget-mib`, default 180).
- First launch may hitch while all images decode on the main thread — intentional baseline behavior, not a fake delay.
- Android SDK may need `sdk.dir` in `local.properties` for command-line builds.
