---
name: android-gallery-perf
description: Implements the CS426 Android image-gallery performance seminar app (Java, Views/XML, Phase 1 eager baseline through tagged Phase 2 RecyclerView optimizations, deterministic datasets, PROJECT_CONTEXT.md). Use when building, optimizing, or documenting this gallery app, working from APP_INSTRUCTIONS.md, or when the user mentions v1-unoptimized, v2-optimized, gallery jank, viewport loading, or seminar benchmarks.
---

# Android Gallery Performance Seminar

## Source of truth

Before editing code, read in order:

1. [APP_INSTRUCTIONS.md](../../../APP_INSTRUCTIONS.md) — full requirements
2. `PROJECT_CONTEXT.md` (if present) — current tag, structure, next step
3. `README.md` (if present) — setup and dataset commands

Follow APP_INSTRUCTIONS.md when this skill and that file disagree.

## Non-negotiable constraints

- **Stack:** Java, Gradle Groovy (`build.gradle`), Android Views + XML. No Compose, no DI frameworks, no Clean Architecture layers, no network, no database.
- **Scope:** one gallery screen + one preview screen; local images only; keep the project small and explainable.
- **Primary experiment:** viewport-based view creation and image loading vs eager full-gallery creation. Measure scrolling/jank later — not memory leaks as the main claim.
- **Memory leaks:** quality requirement in *all* versions. No static/global `Activity`/`View`/adapter/unbounded bitmap refs; clean up executors/listeners; pass image id/index via Intent (never a Bitmap).
- **Benchmarks:** do **not** invent, run, interpret, or claim measured results unless the user explicitly asks. Keep the app deterministic and benchmark-ready only.
- **No fake jank:** no `Thread.sleep()`, busy loops, or deliberate UI-object leaks — even in Phase 1.

## Workflow

### Phase 1 — `v1-unoptimized`

1. Implement gallery + preview with required UI behavior (see Behavior below).
2. Keep intentional bottlenecks:
   - Eager full hierarchy (`ScrollView`/nested rows or `GridLayout`) — **no RecyclerView**
   - Decode/load all gallery images at init into screen-owned (non-static) state
   - Decode original-resolution files for grid cells
   - No reusable cache abstraction
   - Nested/complex item layouts (still visually equivalent to Phase 2)
   - Main-thread decode only if the device still runs the app
3. Ensure datasets are sized so Phase 1 stays runnable; never shrink only Phase 1 data.
4. Commit and tag/branch `v1-unoptimized` before any optimization.
5. Update `PROJECT_CONTEXT.md` and `README.md`.

### Phase 2 — one optimization per Git tag

Preserve user-visible behavior and the same dataset/order every step. Tag after each step:

| Tag | Change |
|-----|--------|
| `v2-step-1-recyclerview` | `RecyclerView` + `GridLayoutManager` + Adapter/ViewHolder |
| `v2-step-2-viewport-loading` | Bind-time load; cancel/ignore on recycle; no stale bitmaps (**primary eval**) |
| `v2-step-3-background-decoding` | Bounded `ExecutorService`; UI updates on main thread; shutdown on destroy |
| `v2-step-4-sized-thumbnails` | `inSampleSize` / display-sized grid decode; preview still uses original file |
| `v2-step-5-bounded-cache` | Bounded `LruCache` keyed by image+size; no Activity/View refs |
| `v2-optimized` | Final verified state |

Do not mix unrelated refactors into an optimization commit.

## Behavior checklist

- Order: oldest top → newest bottom; deterministic (manifest/filename), not raw FS order.
- Square grid cells; `fitCenter`-style (preserve aspect ratio, no crop); same columns/spacing across versions.
- Tap → preview of original source file; left/right arrows; disable/hide at ends; return without duplicate screens.
- Initial scroll at top (deterministic).
- Dataset via Gradle property → `BuildConfig` (e.g. `-PgalleryDataset=easy|mixed`); default documented; no dataset UI.

## Datasets

Scripts under `tools/datasets/` (Python + Pillow, offline, deterministic seed):

- `generate_easy_dataset.py` → 300 uniform square images + `manifest.json`
- `generate_mixed_dataset.py` → 300 varied res/aspect + budget check for Phase 1 decoded memory

Same generated files for any Phase 1 vs Phase 2 comparison. Record seed/commit policy in README.

Manifest item fields: `id`, `filename`, `timestamp`, `width`, `height`.

## Documentation duties

After structural or optimization changes, update `PROJECT_CONTEXT.md` (prefer under 200 lines): current tag, phase status, directory/key-file map, data flow, current bottleneck or step, tag map, dataset selection, files to skip, constraints.

`README.md`: purpose, research question, setup, run/build, dataset commands, Gradle dataset switch, tags, planned tools (Macrobenchmark/`FrameTimingMetric`, Perfetto, Memory Profiler) — no fabricated numbers.

Do not commit `APP_INSTRUCTIONS.md` if project Git rules exclude it; do not commit `build/`, IDE metadata, or benchmark noise.

## Agent do / don't

**Do**

- Prefer few clear Java classes over architecture theater.
- Keep Phase 1 and Phase 2 visually/functionally comparable.
- Record assumptions in README/`PROJECT_CONTEXT.md` instead of silently changing the experiment.

**Don't**

- Start Phase 2 before `v1-unoptimized` is preserved.
- Remove Phase 1 bottlenecks while still on the baseline tag.
- Add auth, network, Compose, albums, search, upload, analytics, or other out-of-scope features.
- Claim an optimization “worked” without group measurements.
