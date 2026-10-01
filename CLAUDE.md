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
Every pipeline stage (0-6) is implemented and `python -m algo.pipeline --config configs/default.yaml` runs end-to-end against the real Tycho data below — not a stub anymore. No `ui/` or `desktop/` code yet.

Key implementation decisions (deviate from the original stub sketch, see each module's docstring for why):
- **Stage 0.5 (new)** `preprocessing/grid.py` — Calibrated products aren't map-projected, so Stage 0's AOI can't crop them by lat/lon directly. Uses the ground-control grid CSV ISRO ships alongside each product (`geometry/calibrated/.../*_g_grd_*.csv`, regular (line,sample)↔(lat,lon) points) to window a huge orbit strip (213595 lines here) down to ~17K lines before any pixel processing. Also shape-matches the REFERENCE crop to the source swath's actual footprint (reproject each corner's lat/lon into the reference's CRS via pyproj) instead of using the whole exported reference tile — a narrow push-broom strip barely overlaps a square AOI export otherwise.
- **Stage 1** `preprocessing/illumination.py` — DEM-based hillshade re-rendering isn't viable: the LRO reference is a pre-blended QuickMap mosaic with no single sun angle to re-target. Falls back to a Gabor-energy structure map, used only by the classical matcher — the learned matcher (LoFTR) runs on the plain tile instead.
- **Stage 2** `pyramid/coarse_to_fine.py` — builds a source pyramid and resamples the reference to match each level's GSD (skips levels needing an unreasonable reference resize), so matching happens at a shared physical scale across the ~20x gap.
- **Stage 3 primary** `matching/learned.py` — kornia's LoFTR. Its `pretrained="outdoor"` hardcodes a dead academic HTTP host; weights are instead downloaded once via `scripts/download_loftr_weights.py` (official kornia HuggingFace mirror) into `algo/models/` (gitignored) and loaded manually.
- **Stage 5** `geometry/robust_fit.py` — homography + `cv2.USAC_MAGSAC` only; DTM orthorectification (`geometry/orthorectify.py`) and sub-pixel refinement are still stubs.

**Known quality ceiling (investigated, not a bug)**: current real-data run gets 5 inliers out of 51 candidate matches. Root-caused by isolating level 0's 32 high-confidence (≥0.5) LoFTR matches and fitting independently: homography RANSAC caps at 5-6/32 inliers from 1px up through 10px reprojection threshold, and swapping to affine (fewer DOF, should be more forgiving of noisy correspondences if the model were the problem) gives the *same* ceiling (4-6/32 even at 20px). That rules out "wrong transform model" or "threshold too strict" as the cause -- it means only ~5-6 of the 32 high-confidence matches are actually mutually geometrically consistent under any reasonable rigid-ish transform. The rest are locally-plausible LoFTR/ORB matches that don't hold up globally, consistent with the known failure mode of matching repetitive, self-similar cratered terrain (small craters/rocks look alike in many places). `reproj_threshold_px` was bumped 1.0→3.0 (1.0 was unrealistically strict for a ~68m/px coarse level and cost 1-2 legitimate inliers for no real precision gain) -- a small honest improvement, not a fix for the ceiling itself.

Real next levers, roughly in order of expected value: (1) a less self-similar AOI/sub-region for a cleaner demo case, (2) sub-pixel refinement + a second RANSAC pass seeded by the current 5 inliers to pull in near-miss correspondences, (3) DTM orthorectification (unimplemented) to remove relief-induced parallax, which may itself be inflating the apparent inconsistency among otherwise-correct matches on this crater's high-relief terraced walls.

## Data on disk — Tycho AOI, all three slots real
- **Source** `data/raw/chandrayaan2/tmc2/ch2_tmc_ncn_20240124T0838058678_d_img_d18/` — Calibrated TMC-2 image, orbit 19674, 4.2 m/px. This is the exact companion image the Tycho DTM below was derived from (same orbit, same sun angle) — found by matching orbit/timestamp after two off-AOI (polar) downloads turned up no Tycho coverage via direct AOI search.
- **Reference** `data/raw/lro_reference/tycho/wac_nac/` — real LRO WAC export (PNG+VRT, 86 m/px, orthographic projection).
- **DEM** `data/dem/tycho/` — real TMC-2 Derived DTM (10 m/px elevation).
- Scale ratio source/reference ≈ 20×.
- Set aside, not wired in (different AOIs, kept for reference): `data/raw/chandrayaan2/ohrc/` (Calibrated OHRC, South Pole) and `data/raw/chandrayaan2/tmc2/ch2_tmc_ncf_.../` (Calibrated TMC-2, North Pole). Both still useful — they validated `parse_pds4_label` generalizes across instruments with zero instrument-specific code.
- `data/raw/lro_reference/tycho/catalog/` — QuickMap product-search catalogs (GeoJSON, no pixel data), useful for picking a higher-res NAC tile later.

Lesson for next AOI: ISSDC's Calibrated-product catalog skews toward landing-site targets (poles); a Derived DTM's label records the `imaging_orbit_number` of the Calibrated image it was built from, so search by that orbit/timestamp rather than by AOI box alone.
