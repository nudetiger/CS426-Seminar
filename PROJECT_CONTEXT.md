# Project Context — CS426 Gallery

## Project summary

Small Java / Views Android image gallery for a seminar on scrolling performance: compare eager full-gallery creation (`v1-unoptimized`) with incremental viewport-based optimizations (`v2-*`). Local datasets only; no network or database.

## Current checked-out version

`v2-step-6-scroll-aware-prefetch`

## Current phase status

- **Done:** Through Phase 2 step 6 — defer main-thread bitmap applies while flinging; prefetch ~2 rows into `ThumbnailCache`; larger item view cache / layout prefetch.
- **Next:** Final verify / tag `v2-optimized` when the group accepts this as the complete optimized build.
- **Later:** Seminar benchmarks comparing `v1-unoptimized` vs optimized tags (quiet host; warm vs cold scroll).

## Architecture summary

Two activities (`MainActivity`, `PreviewActivity`). Metadata flows through `GalleryRepository` / `DatasetManifestReader` from asset manifests. `ImageDecoder` supports full and display-sized asset decode. Gallery UI is a `RecyclerView` grid; `GalleryAdapter` uses a bounded background executor plus `ThumbnailCache` for bind-time loads, with scroll-aware UI applies and off-screen prefetch.

## Directory map

| Path | Role |
|------|------|
| `app/` | Android application module |
| `app/src/main/java/com/cs426/gallery/` | Activities + gallery adapter |
| `.../data/` | `GalleryImage`, repository, manifest reader |
| `.../image/` | Decode helpers + `ThumbnailCache` |
| `app/src/main/res/layout/` | Gallery, preview, item XML |
| `app/src/main/assets/datasets/` | Runtime easy/mixed assets (manifest + images) |
| `tools/datasets/` | Python generators + asset sync helper |
| `tools/benchmark/` | Automated adb benchmark CLI → CSV |
| `datasets/generated/` | Generator output (images usually not committed) |
| `docs/benchmark/` | Benchmark CSV output (contents gitignored) |
| `PROJECT_CONTEXT.md` | This navigation map |
| `README.md` | Setup, run, and benchmark docs |

## Key files/classes

| Item | Role |
|------|------|
| `MainActivity` | RecyclerView host; scroll listener defers UI applies + triggers prefetch; owns executor + cache |
| `GalleryAdapter` | Bind-time async display-sized decode; cache hit/miss; defer apply while flinging; prefetch into cache |
| `ThumbnailCache` | Bounded `LruCache` keyed by `imageId@sizePx`; recycles on eviction; no Activity/View refs |
| `GalleryGridSpacingDecoration` | Column/row spacing matching Phase 1 gaps |
| `PreviewActivity` | Original-file preview + ActionBar Up; arrows + finger-follow swipe; boundary-aware |
| `GalleryImage` | Immutable manifest row |
| `GalleryRepository` | Selected dataset → ordered list + asset paths |
| `DatasetManifestReader` | Parse/sort `manifest.json` |
| `ImageDecoder` | `decodeAssetFull` (preview) + `decodeAssetForDisplay` (grid / `inSampleSize`) |
| `BenchLog` | `GalleryBench` log markers for the Python harness |
| `activity_main.xml` | `RecyclerView` gallery host |
| `activity_preview.xml` | Dual `ImageView` merge-swipe layer + `fitCenter` + prev/next |
| `item_gallery_image.xml` | Nested cell layout (unchanged visually) |
| `app/build.gradle` | AGP module; `-PgalleryDataset=` → `BuildConfig` |
| `gradle.properties` | Default `galleryDataset=mixed` |

## Data flow

`manifest.json` (assets) → `DatasetManifestReader` → `GalleryRepository` → `MainActivity` (metadata + executor + cache) → `GalleryAdapter.onBind` / prefetch → cache hit or background `decodeAssetForDisplay` → main-thread apply when idle → Intent (id/index) → `PreviewActivity` → `decodeAssetFull` (original file)

## Current performance behavior

After step 6:

1. **Views:** recycled via `RecyclerView` / `ViewHolder`; larger item view cache + layout manager prefetch.
2. **Viewport load:** decode only on bind/prefetch miss; generation/id ignore avoids stale apply.
3. **Sized thumbnails:** grid uses `inSampleSize` targeted at cell pixels; preview still full original.
4. **Bounded cache:** `LruCache` (~1/8 max heap) keyed by image+size; eviction recycles bitmaps; cleared on destroy.
5. **Scroll-aware apply:** while dragging/settling, skip `setImageBitmap` for decode completions (cache still fills); on idle, apply cache hits to visible cells.
6. **Prefetch:** ~2 rows above/below visible window decode into cache without binding.
7. Nested `item_gallery_image` layout.
8. **Background decode:** bounded fixed pool (2–4 threads); UI updates on main thread; `shutdownNow()` on destroy.

## Version/tag map

| Tag | Status |
|-----|--------|
| `v1-unoptimized` | Created (eager ScrollView baseline) |
| `v2-step-1-recyclerview` | Created |
| `v2-step-2-viewport-loading` | Created (primary eval) |
| `v2-step-3-background-decoding` | Created |
| `v2-step-4-sized-thumbnails` | Created |
| `v2-step-5-bounded-cache` | Created |
| `v2-step-6-scroll-aware-prefetch` | Created (this checkout) |
| `v2-optimized` | Planned (final verified alias) |

## Dataset selection

- Gradle property `galleryDataset` = `easy` \| `mixed` (default **mixed** in `gradle.properties`).
- Exposed as `BuildConfig.GALLERY_DATASET`.
- Example: `./gradlew :app:assembleDebug -PgalleryDataset=easy`
- Generators use seed **2026**. Easy: 256×256 (~75 MiB ARGB decoded). Mixed: 210 low / 60 medium / 30 high long-edge tiers; budget **180 MiB** (~57.5 MiB estimated).
- Grid: **4 columns** (`R.integer.gallery_column_count`), square cells, `fitCenter`.
- Theme knobs (`themes.xml` / `colors.xml`): `galleryBackground` (gap), `galleryCellLetterbox`, `previewLetterbox`.

## Benchmark-readiness notes

- Content descriptions include image id on gallery items and preview.
- Initial scroll position is top of gallery.
- In-app markers: `gallery_ready`, `preview_ready`, `preview_navigate` via `BenchLog` (`GalleryBench` tag); `reportFullyDrawn()` after grid submit (visible cells may still fill in async; prefetch starts after submit).
- Runner: `python tools/benchmark/run_benchmark.py` → `{prefix}_runs.csv` + `{prefix}_summary.csv` under `docs/benchmark/`.
- Do not invent or commit fabricated metrics.
- Scroll comparisons are sensitive to host load (emulator shares CPU/GPU); prefer quiet-host re-runs for v1 vs v2.

## Files to skip

`build/`, `.gradle/`, `.idea/`, `local.properties`, generated images under `datasets/generated/**/images/` and mirrored asset images, `APP_INSTRUCTIONS.md` (local instructions; do not commit per project rules), IDE/profiler noise.

## Important constraints

Java; Gradle Groovy; Views/XML; no Compose; no DI/Clean Architecture theater; no network/DB; no static Activity/View/bitmap collections; no fake jank (`sleep`, busy loops); keep Phase 1 runnable via dataset sizing.
