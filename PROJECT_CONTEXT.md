# Project Context — CS426 Gallery

## Project summary

Small Java / Views Android image gallery for a seminar on scrolling performance: compare eager full-gallery creation (`v1-unoptimized`) with incremental viewport-based optimizations (`v2-*`). Local datasets only; no network or database.

## Current checked-out version

`phase1-wip` (Phase 1 gallery + preview wired; not yet tagged `v1-unoptimized`)

## Current phase status

- **Done:** Project structure, datasets (easy/mixed generators + assets), Phase 1 eager gallery (`ScrollView` rows), full-res decode-all-at-init on main thread, preview with ActionBar Up, arrows, and intentional decode-on-swipe merge drag.
- **Next:** Manual smoke-test on device/emulator → commit and tag `v1-unoptimized`.
- **Later:** Phase 2 one-tag-at-a-time optimizations.

## Architecture summary

Two activities (`MainActivity`, `PreviewActivity`). Metadata flows through `GalleryRepository` / `DatasetManifestReader` from asset manifests. `ImageDecoder` opens local assets. Phase 1 builds an eager `ScrollView` + nested row/`item_gallery_image` hierarchy (no `RecyclerView`). Phase 2 adapter/cache classes are intentionally absent.

## Directory map

| Path | Role |
|------|------|
| `app/` | Android application module |
| `app/src/main/java/com/cs426/gallery/` | Activities |
| `.../data/` | `GalleryImage`, repository, manifest reader |
| `.../image/` | Decode helpers |
| `app/src/main/res/layout/` | Gallery, preview, item XML |
| `app/src/main/assets/datasets/` | Runtime easy/mixed assets (manifest + images) |
| `tools/datasets/` | Python generators + asset sync helper |
| `datasets/generated/` | Generator output (images usually not committed) |
| `docs/benchmark/` | Group results later |
| `PROJECT_CONTEXT.md` | This navigation map |
| `README.md` | Setup and run docs |

## Key files/classes

| Item | Role |
|------|------|
| `MainActivity` | Eager ScrollView grid; owns decoded bitmap list; opens preview via Intent id/index |
| `PreviewActivity` | Original-file preview + ActionBar Up; arrows + finger-follow swipe; boundary-aware; recycles screen bitmaps on change/destroy |
| `GalleryImage` | Immutable manifest row |
| `GalleryRepository` | Selected dataset → ordered list + asset paths |
| `DatasetManifestReader` | Parse/sort `manifest.json` |
| `ImageDecoder` | Full asset decode (Phase 1 grid/preview) |
| `activity_main.xml` | `ScrollView` + vertical container |
| `activity_preview.xml` | Dual `ImageView` merge-swipe layer + `fitCenter` + prev/next |
| `item_gallery_image.xml` | Nested cell layout for Phase 1 |
| `app/build.gradle` | AGP module; `-PgalleryDataset=` → `BuildConfig` |
| `gradle.properties` | Default `galleryDataset=mixed` |
| `generate_easy_dataset.py` | 300×256 square JPEGs + manifest |
| `generate_mixed_dataset.py` | 300 varied res/aspect + decoded budget check |
| `sync_datasets_to_assets.py` | Copy generated → `app/.../assets/datasets/` |

## Data flow

`manifest.json` (assets) → `DatasetManifestReader` → `GalleryRepository` → `MainActivity` (decode all + eager views) → Intent (id/index) → `PreviewActivity` → `ImageDecoder` (original file)

## Current performance behavior

Phase 1 intentional bottlenecks active:

1. Full hierarchy created eagerly (`ScrollView` + horizontal rows; no `RecyclerView`).
2. All gallery images decoded at init into non-static `MainActivity` state.
3. Original-resolution decode for grid cells (no `inSampleSize`).
4. No reusable cache abstraction.
5. Nested `item_gallery_image` layout.
6. Main-thread decode during gallery `onCreate`.

## Version/tag map

| Tag | Status |
|-----|--------|
| `v1-unoptimized` | Not created (ready to tag after smoke-test) |
| `v2-step-1-recyclerview` | Planned |
| `v2-step-2-viewport-loading` | Planned (primary eval) |
| `v2-step-3-background-decoding` | Planned |
| `v2-step-4-sized-thumbnails` | Planned |
| `v2-step-5-bounded-cache` | Planned |
| `v2-optimized` | Planned |

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
- Results directory: `docs/benchmark/` (empty for now).
- Do not invent or commit fabricated metrics.

## Files to skip

`build/`, `.gradle/`, `.idea/`, `local.properties`, generated images under `datasets/generated/**/images/` and mirrored asset images, `APP_INSTRUCTIONS.md` (local instructions; do not commit per project rules), IDE/profiler noise.

## Important constraints

Java; Gradle Groovy; Views/XML; no Compose; no DI/Clean Architecture theater; no network/DB; no static Activity/View/bitmap collections; no fake jank (`sleep`, busy loops); keep Phase 1 runnable via dataset sizing.
