# algo — registration pipeline

Core CV package: registers Chandrayaan-2 strips (OHRC 0.25 m, TMC-2 5 m, IIRS 98 m) against LRO references (NAC / WAC
mosaics) across differences in **illumination, viewpoint and scale**. Design and per-obstacle write-up:
[../docs/architecture.md](../docs/architecture.md). Measurements: [../docs/benchmark.md](../docs/benchmark.md) (synthetic,
known transform) and [../docs/results.md](../docs/results.md) (every real project).

## Setup

Use Python 3.11 (rasterio wheel availability lags on newer versions). No torch is needed to run.

```bash
cd algo
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
# LoFTR runs from models/loftr_*.onnx (gitignored). Build them once (needs torch+kornia, see requirements-export.txt):
pip install -r requirements-export.txt
python scripts/export_loftr_onnx.py
```

## Run

```bash
python -m algo.pipeline --config configs/ohrc_20260721.yaml      # one project
python scripts/run_all.py                                        # every project in configs/, recorded as app runs
python -m algo.api.server                                        # the API the desktop app talks to (port 8000)
```

A run writes `data/results/<run_id>/`: `registered.tif` (source resampled onto the reference grid, georeferenced),
`tiepoints_geo.csv`, `transform.json` (homography + non-rigid field), `metrics.json`, `matches.csv`; the visualization set is
rendered on demand by the API (or `python scripts/render_all_viz.py`).

## Projects (`configs/`)

| config | what it is |
|---|---|
| `default`, `copernicus`, `tycho_relit` | TMC-2 vs 5 m LROC NAC ROI mosaics (`tycho_relit` adds the DEM re-lit with the source's Sun) |
| `strip_n45e10`, `n40e13`, `n47e09`, `n41e109`, `n27w093` | TMC-2 strips vs LRO WAC 100 m (fore/aft views included) |
| `strip_n73e012`, `n77e200`, `n79e249`, `n81e233` | north-polar TMC-2 (Sun 7-13 deg) vs LRO WAC; `*_ce2` = same strips vs Chang'e-2 7 m (cross-check, not LRO); `n79e249`/`n81e233` are RAW products registered from label corners |
| `ohrc_20260721` / `20260628` / `20241115` / `20260729` | OHRC south polar vs LRO NAC polar mosaic (4.18 m) with the LOLA DEM re-lit at the source's Sun; only the lit line ranges |
| `ohrc_20260728` | OHRC pass in permanent shadow: the refusal example ("no usable contrast") |
| `iirs_s14e156`, `iirs_s31e155` | IIRS hyperspectral cubes (band-averaged 0.9-1.6 um) vs WAC 100 m |

New project: `python scripts/make_config.py <name> <product dir> <reference.tif> [--rows R0 R1] [--dem dem.tif --relit]`.
References: `scripts/fetch_wac_reference.py` (equatorial WAC 100 m), `scripts/fetch_trek_polar_nac.py` (polar NAC / WAC / Chang'e-2
tiles), `scripts/fetch_lola_dem_window.py` (LOLA DEM windows), `scripts/download_lro_reference.py` (LROC ROI products).

## Layout

```
algo/
├── src/algo/
│   ├── pipeline.py            # orchestration (prior-guided path; blind LoFTR/ORB path kept as `registration.mode: blind`)
│   ├── registration.py        # register(): matching -> full model fit -> inliers. Shared with the benchmark
│   ├── export.py              # registered.tif, tiepoints_geo.csv
│   ├── preprocessing/         # labels (sun, pixel size, view angles), control grid / label-corner geolocation, decimated reads
│   ├── matching/              # prior_guided.py (the matcher), structure.py (representations + NCC); legacy: learned/classical/crater
│   ├── illumination/          # relight.py (DEM -> image at a given Sun), dem.py (DEM on the reference grid)
│   ├── geometry/              # model_fit.py, nonrigid.py, parallax.py, analysis.py (reliability checks), warp.py
│   ├── benchmark/             # synthetic ground-truth scenes, runner, suites, report
│   ├── api/                   # FastAPI server, visualization, previews
│   ├── evaluation/            # metrics.json, matches.csv, transform.json
│   └── utils/
├── configs/                   # one yaml per project
├── scripts/                   # data fetching, run_all, cross_check, make_config, ...
└── tests/
```

## Test

```bash
pytest tests/ -v      # ~10 min: test_pipeline runs a real strip; the rescue/scale tests use large synthetic images
```

`test_pipeline.py::test_run_end_to_end` and the `*_real` checks use the local Tycho data and skip when it is absent.

## Benchmarks and cross-checks

```bash
python -m algo.benchmark.suites illumination --workers 6 --seeds 3    # also: viewpoint, prior, scale, combined
python -m algo.benchmark.report                                        # -> data/benchmark/summary.json, docs/benchmark.{md,png}
python scripts/cross_check.py reference strip_n77e200 strip_n77e200_ce2    # same strip, two independent references
python scripts/cross_check.py prior strip_n45e10                          # wrong starting guesses
```
