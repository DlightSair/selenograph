# algo — registration pipeline

Core CV/DL package. See [../docs/architecture.md](../docs/architecture.md) for the full design.

## Setup

Use Python 3.11 (rasterio/torch wheel availability lags on newer versions).

```bash
cd algo
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python scripts/download_loftr_weights.py   # ~46MB; kornia's own download URL is a dead host, see script docstring
```

## Test

```bash
pytest tests/ -v
```

`test_metadata.py` and `test_pipeline.py::test_run_end_to_end` run against the real Tycho source/reference/DEM data under `../data/` — skipped automatically if that data isn't present. `test_run_end_to_end` is slow (several minutes since the reference-data swap to a near-native-resolution NAC mosaic — see CLAUDE.md's "Reference data swap" — windowed-reads a 1.7GB source file and runs classical/crater matching at close to full resolution, not just LoFTR).

## Layout

```
algo/
├── src/algo/
│   ├── pipeline.py          # end-to-end orchestration
│   ├── preprocessing/       # Stage 0-1: metadata parsing, illumination normalization
│   ├── pyramid/             # Stage 2: coarse-to-fine scale alignment
│   ├── matching/            # Stage 3-4: classical + learned matchers, ANMS
│   ├── geometry/            # Stage 5: RANSAC/MAGSAC++, homography, DTM orthorectification
│   ├── evaluation/          # Stage 6: RMSE, inlier ratio, spatial uniformity
│   └── utils/               # shared IO (PDS label parsing, raster IO)
├── configs/default.yaml     # AOI, instrument, and pipeline parameters
├── models/                  # pretrained weights (e.g. LoFTR) — not committed
├── scripts/                 # data download / organization helpers
├── notebooks/                # exploration
└── tests/
```

## Run

```bash
python -m algo.pipeline --config configs/default.yaml
```

Every stage is implemented and runs end-to-end against real data, plus four accuracy-improvement stages (crater-constellation matching, geometric-consistency boosting, DTM relief weighting, sub-pixel refine/densify) — see `CLAUDE.md` for what they do and the current match-quality caveats. Not implemented yet: DTM-based orthorectification (`geometry/orthorectify.py`) — homography + MAGSAC++ only so far.
