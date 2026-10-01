# algo — registration pipeline

Core CV/DL package. See [../docs/architecture.md](../docs/architecture.md) for the full design.

## Setup

```bash
cd algo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

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

(stub — `pipeline.py` currently just wires the stages together; each stage is a TODO)
