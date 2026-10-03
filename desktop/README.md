# desktop

Flutter desktop app (Windows/Linux/macOS) for the registration pipeline. Talks to a local
FastAPI server (`algo.api.server`, inside `algo/`'s own venv) over `http://127.0.0.1:8000` —
the app has no Python embedded in it, it just drives the existing CLI pipeline over HTTP.

Design: brutalist / instrument-panel — thick square borders, no shadows, one accent color (signal
red) for actions and errors. Typography is deliberately split: a plain sans font for everything
you read and scan (nav, buttons, panel titles, hints, prose), monospace reserved for actual data
(numbers, coordinates, run IDs, file paths, the homography matrix). An earlier pass used monospace
for all of it, including small letter-spaced uppercase labels — legible as a style statement, but
measurably harder to read at a glance; see the comment at the top of `lib/theme/brutalist_theme.dart`
(`monoStyle` vs `uiStyle`/`labelStyle`/`bodyStyle`). Interactive elements (buttons, project cards,
nav items, run rows) all have a hover state now too — see `lib/widgets/hoverable.dart`.

## Status

`lib/` is hand-written and complete (theme, models, API client, home + results screens).
**The Flutter/platform scaffolding (`windows/`, `linux/`, `macos/`, `test/`,
`analysis_options.yaml`, `.gitignore`) has not been generated yet** — this machine doesn't have
the Flutter SDK installed, so it couldn't be run here. One command fixes that, and it's safe to
run on top of what's already here (see below).

## First-time setup

1. Install Flutter (https://docs.flutter.dev/get-started/install) and make sure desktop support
   is enabled:
   ```bash
   flutter config --enable-windows-desktop --enable-linux-desktop --enable-macos-desktop
   flutter doctor
   ```
2. From this directory, generate the missing platform folders. `flutter create .` on a directory
   that already has a `pubspec.yaml`/`lib/` is the documented way to add platform support to an
   existing project — it fills in what's missing (`windows/`, `linux/`, `macos/`,
   `analysis_options.yaml`, `.gitignore`, `test/`) and does not overwrite the existing
   `lib/main.dart` or `pubspec.yaml`:
   ```bash
   flutter create --platforms=windows,linux,macos .
   ```
   Check `git status` afterwards and review the diff before committing — if anything looks like
   it clobbered a hand-written file, stash it and ask before proceeding.
3. Install the Dart dependencies:
   ```bash
   flutter pub get
   ```

## Running

```bash
flutter run -d windows   # or -d linux / -d macos
```

The app is designed to feel offline/self-contained — the server is an implementation detail the
UI hides, not something you manage. On launch you get a splash screen ("PREPARING WORKSPACE"
etc.) while `lib/screens/splash_screen.dart` connects: checks the backend, launches it if needed,
and only mounts the actual app once it's confirmed reachable. No flicker, no technical jargon in
the normal path — the main UI (sidebar + Projects) never has to know a local server is involved.

On Windows, auto-start goes through `cmd /c start`, which opens a separate **"Lunar Registration
Server" console window** — that's intentional, not a bug: `flutter run` hosts the app inside a
Windows Job Object, and a child process started the naive way (even "detached") stays tied to that
job and gets killed a few seconds later when the job tears down. Routing through `start` escapes
it, and as a side benefit the server's own output/crashes are directly visible in that window
instead of silently swallowed. On Linux/macOS it launches properly detached with output captured
to a log file instead (no job-object issue there).

If it still can't connect after ~45s, the splash screen shows a plain "could not start" message
with a Retry button — technical specifics (paths searched, log location) are behind a collapsed
"+ TECHNICAL DETAILS" toggle, not shown by default. Fallbacks if auto-start genuinely can't find
it:

- Windows: double-click `algo/start_server.bat` (same `cmd /c start` mechanism, standalone).
- Or by hand, from `algo/`, inside its venv:
  ```bash
  ./.venv/Scripts/python.exe -m algo.api.server   # Windows
  # ./.venv/bin/python -m algo.api.server         # Linux/macOS
  ```

## What it does

- **Splash screen**: owns the entire backend-connection story (see above). This is the only
  screen that ever shows server-related messaging.
- **Projects** (sidebar): a grid of AOI projects — each is one `algo/configs/*.yaml`. Click
  **+ New project** to register a new AOI: a form for the lat/lon box, source instrument, and the
  paths to an already-downloaded PDS4 source product directory and reference mosaic file. Each
  path field has a **Browse…** button (native OS folder/file picker, via `file_selector`) that
  converts the picked absolute path to one relative to `algo/`, matching the convention every
  existing config uses. Submitted to a `POST /configs` endpoint that validates the paths actually
  exist and writes the YAML. There's no generic "pick any picture" import, even with a picker in
  the loop — the pipeline only understands PDS4-labeled Chandrayaan-2 products (see
  `algo/src/algo/utils/io.py`), not arbitrary images, so you're still pointing at an
  already-downloaded product directory / GeoTIFF, just without typing the path by hand.
- **Project detail**: the whole page scrolls as one unit (no fixed-height split panes, so it can't
  overflow regardless of window size). Right column: the **Latest run** card (whatever run is
  newest, with inline metrics — or a "no reliable fit" note and its reason — and the primary
  action) and the AOI's source/reference imagery (`GET /configs/{name}/preview.png`, generated
  straight from the config, no run required) below it. Left column: facts about the project — AOI
  centre/extent/area, the source and reference products' pixel size and image size (read from the
  real products via `GET /configs/{name}/details`), **viewing geometry** (camera — nadir / forward
  +25° / aft −25° —, roll, pitch, yaw, altitude), **illumination** (sun azimuth/elevation, with a
  note when the Sun is under 5° because shading is then almost pure topography), the expected
  source-to-reference scale, the registration mode with small on/off chips for the **re-lit DEM**,
  **DEM parallax** and **non-rigid** options, and run activity (paths are selectable/copyable).
  Every one of those fields is optional: a product that doesn't provide it just doesn't show the
  row. There is no past-runs list: a project is one fixed AOI and the pipeline has no exposed
  randomness, so only the latest run matters and **Re-run** is a secondary action.
- **Results screen**: metrics as instrument-style readouts, each with a one-line plain-language
  hint: RMSE, **held-out error** (accuracy on tiles the fit never saw — the honest number),
  inlier count/ratio, match count, spatial-uniformity CoV, the **non-rigid correction** (rms shift
  beyond the homography and the cross-validated gain, or "not needed" when the extra field was
  rejected), the **matching representation** the scene vote picked (intensity / edges / cfog, with
  a plain explanation) and the **scale** (source vs. reference metres per pixel and their ratio,
  noting block-averaging of huge strips). Readouts only appear when the run has the data, so older
  runs look as they always did. Below them, a **"How it was matched"** panel shows the stage
  table (working resolution, tiles tried / matched / inliers), the representation vote as small
  agreement bars, whether the illumination-aware DEM layer and the terrain-parallax model were
  used (with the fitted-vs-expected parallax coefficients), and a note when the rescue search had
  to recover a badly wrong starting guess. The raw homography matrix is shown too (selectable/
  copyable). A failed run shows the captured stderr tail.
- **No reliable fit**: when a run completes but `metrics.failure` is set (shadowed strip, no
  consistent global shift, tile measurements that don't agree...), the readouts are replaced by a
  calm **"No reliable fit"** panel with the reason in plain words and a one-line hint at the usual
  cause, the status pill reads "no fit" instead of "done", and a "What was tried" panel keeps the
  stage table and representation vote for diagnosis. The visualization section is not requested
  for such a run (`/runs/{id}/viz` fails when there is no fit).
- **Result visualization** (`GET /runs/{id}/viz` and `/viz/{name}.png`, rendered by
  `algo/src/algo/api/visualization.py`, cached under the run's `viz/`; the first view of a run takes
  seconds for a WAC strip and a few minutes for a 100 km NAC-referenced one — `algo/scripts/render_all_viz.py` pre-renders them). An **"Is this fit reliable?"** panel runs sanity checks that don't depend on
  judging a picture: transform conditioning, scale vs. the source/reference pixel-size ratio, the
  number of *independent* anchors (near-duplicate densified points merged), and agreement with the
  independent control-grid prior, plus the transform's scale/rotation numbers. RMSE alone can't be
  trusted, since a collapsed transform scores a low RMSE. Below it are up to thirteen **separate images, each
  in its own tile with its own zoom window** (the DEM re-lit with the source's Sun and the non-rigid correction appear only when the run used them): the source footprint and warped pixel grid drawn on
  the reference next to the control-grid prior; a magenta/green false-colour overlay and a
  checkerboard (local-contrast-normalized so the sun-angle difference drops out); native-resolution
  close-ups at matched locations; the warped source; the matching reference region; numbered anchors
  on source and reference; and residual-error and prior-agreement charts.
- **Images**: shown as a static tile; click it to open a near-full-window dialog with scroll/pinch
  zoom (up to 16x), drag-to-pan and a reset button. Zooming never happens inline, because an
  always-interactive image embedded in a scrollable page fights the page's own scroll/pan gesture;
  the dialog is the only place that gesture is unambiguous.
- **Benchmark** (sidebar): the synthetic ground-truth benchmark from `GET /benchmarks` (produced
  offline by `python -m algo.benchmark.suites <suite>` / `python -m algo.benchmark.report`; a 404
  shows a "No benchmark yet" empty state with those commands). An intro explains what is measured:
  synthetic scenes built from real lunar terrain with a known truth, one difficulty varied at a
  time, success = under 1.5 reference px RMS. The **Variants** legend (from `variant_notes`) doubles
  as show/hide toggles for every chart. Each swept difficulty gets a panel with a line chart (drawn
  with `CustomPaint`, no chart dependency: x = the swept value, y = median RMS error in reference
  px on a log scale, one line per variant with its success rate printed at any point below 100%, a
  dotted red line at the success threshold) and a compact table underneath (rows = swept values,
  columns = variants, cells like "100% · 0.12 px").
- **About** (sidebar): static project description.

Motion: page navigation fades/slides in app-wide (set once on the theme, not per screen), buttons
scale slightly on hover/press, and sections fade-and-rise in with a short stagger on load — small
cues so actions and navigation changes don't feel like a silent flat cut.

## Known limitations (MVP)

- Progress is coarse — "running" vs "done"/"error", no per-stage percentage. The pipeline itself
  doesn't emit progress events; adding that would mean instrumenting `algo.pipeline.run`, not just
  the UI.
- One run at a time (the server enforces this — these are heavy LoFTR/rasterio jobs, not worth
  racing).
- `file_selector` (native OS file/folder dialogs) and `path` were just added to `pubspec.yaml` —
  run `flutter pub get` again to fetch them. This is a new class of risk versus the rest of
  `lib/`: it's a native plugin with platform-specific code, which can't be verified without the
  Flutter SDK installed on this machine the way the pure-Dart code was. If `flutter run` fails
  specifically on the file picker, that's the first place to look.
