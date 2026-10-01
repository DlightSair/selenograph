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
- `data/raw/lro_reference/tycho/wac_nac/` — real LRO WAC reference export (PNG+VRT, 86 m/px, orthographic projection), full Tycho crater. This is the reference/fixed image.
- `data/raw/lro_reference/tycho/catalog/` — QuickMap product-search catalogs (GeoJSON footprints + metadata, no pixel data) for candidate WAC/NAC frames over Tycho; useful for picking a higher-res NAC tile later.
- Still needed: a Calibrated **source** image (OHRC or TMC-2) from ISSDC chmapbrowse, over the same Tycho AOI — see `algo/scripts/download_chandrayaan2.py`.
