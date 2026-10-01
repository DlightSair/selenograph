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
Stage 0 (`preprocessing/metadata.py`, `utils/io.py`) implemented and runs end-to-end (`load_metadata`) against real source + reference + DEM, all wired through `configs/default.yaml`. Every other `algo/` stage is still a stub (`NotImplementedError`). No `ui/` or `desktop/` code yet.

## Data on disk — Tycho AOI, all three slots real
- **Source** `data/raw/chandrayaan2/tmc2/ch2_tmc_ncn_20240124T0838058678_d_img_d18/` — Calibrated TMC-2 image, orbit 19674, 4.2 m/px. This is the exact companion image the Tycho DTM below was derived from (same orbit, same sun angle) — found by matching orbit/timestamp after two off-AOI (polar) downloads turned up no Tycho coverage via direct AOI search.
- **Reference** `data/raw/lro_reference/tycho/wac_nac/` — real LRO WAC export (PNG+VRT, 86 m/px, orthographic projection).
- **DEM** `data/dem/tycho/` — real TMC-2 Derived DTM (10 m/px elevation).
- Scale ratio source/reference ≈ 20×.
- Set aside, not wired in (different AOIs, kept for reference): `data/raw/chandrayaan2/ohrc/` (Calibrated OHRC, South Pole) and `data/raw/chandrayaan2/tmc2/ch2_tmc_ncf_.../` (Calibrated TMC-2, North Pole). Both still useful — they validated `parse_pds4_label` generalizes across instruments with zero instrument-specific code.
- `data/raw/lro_reference/tycho/catalog/` — QuickMap product-search catalogs (GeoJSON, no pixel data), useful for picking a higher-res NAC tile later.

Lesson for next AOI: ISSDC's Calibrated-product catalog skews toward landing-site targets (poles); a Derived DTM's label records the `imaging_orbit_number` of the Calibrated image it was built from, so search by that orbit/timestamp rather than by AOI box alone.
