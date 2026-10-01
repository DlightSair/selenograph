# CLAUDE.md

SIH PS 26166 — register Chandrayaan-2 optical imagery (OHRC/TMC-2/IIRS) against LRO reference imagery despite illumination, viewpoint, and scale differences.

## Structure
- `algo/` — core registration pipeline, shared by every frontend. Stages: metadata → illumination norm → pyramid → matching (learned+classical) → geometry fit → eval. Design rationale: `docs/architecture.md`.
- `ui/` — **website demo**: small/cropped sample images only, for live judging without install.
- `desktop/` — **desktop app** (planned, not yet created): full-resolution local processing (large rasters, optional GPU), wraps `algo` directly.
- `data/` — local only, gitignored.

## Conventions
- All CV/DL logic stays in `algo/`; `ui/` and `desktop/` call it as a library — never duplicate pipeline logic across frontends.
- Output: GeoTIFF + CSV/JSON + PNG overlays under `data/results/<run_id>/`. Never PDS.
- Run: `python -m algo.pipeline --config algo/configs/default.yaml`

## Status
Stage 0 (`preprocessing/metadata.py`, `utils/io.py`) implemented and tested against a real TMC-2 DTM product in `data/dem/tycho/`. Every other `algo/` stage is still a stub (`NotImplementedError`). No `ui/` or `desktop/` code yet.

## Data on disk
- `data/dem/tycho/` — real TMC-2 Derived DTM (10 m/px elevation), covers Tycho crater AOI. Used as Stage 1/5 DEM input, not a source image.
- Still needed: a Calibrated source image (OHRC or TMC-2) and an LRO WAC/NAC reference export, both over the same Tycho AOI — see `algo/scripts/download_*.py`.
