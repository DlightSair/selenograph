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
Scaffold only — every `algo/` stage is a stub (`NotImplementedError`). No `ui/` or `desktop/` code yet.
