# CLAUDE.md

SIH PS 26166 — register Chandrayaan-2 optical imagery (OHRC/TMC-2/IIRS) against LRO reference imagery despite illumination, viewpoint, and scale differences.

## Structure
- `algo/` — core registration pipeline, shared by every frontend. Stages: metadata → illumination norm → pyramid → matching (learned+classical) → geometry fit → eval. Design rationale: `docs/architecture.md`.
- `ui/` — **website demo**: small/cropped sample images only, for live judging without install.
- `desktop/` — **desktop app** (Flutter, Windows/Linux/macOS): drives `algo.api.server` over localhost; project list, per-project facts, results with reliability checks and visualizations, a Benchmark page. See `desktop/README.md`.
- `data/` — local only, gitignored.

## Conventions
- All CV/DL logic stays in `algo/`; `ui/` and `desktop/` call it as a library — never duplicate pipeline logic across frontends.
- Output: GeoTIFF + CSV/JSON + PNG overlays under `data/results/<run_id>/`. Never PDS.
- Run: `python -m algo.pipeline --config algo/configs/default.yaml`

## Status
Every pipeline stage is implemented and `python -m algo.pipeline --config configs/default.yaml` runs end-to-end. **Read "Problem-statement coverage" below first**: it describes the current default pipeline (prior-guided dense matching + illumination-aware layers + non-rigid/parallax model) and supersedes the older sections on this page wherever they disagree. `docs/architecture.md` is the design write-up, `docs/benchmark.md` the synthetic ground-truth measurements, `docs/results.md` every real project. `ui/` (web demo) is still not started.

Four accuracy-improvement stages were added on top of that first working run (see "Accuracy improvements" below): `matching/crater.py`, `geometry/consistency.py`, `preprocessing/relief.py`, `geometry/refine.py`. The reference data was then swapped for a much higher-resolution real product (see "Reference data swap" below) — read that section first, it supersedes most of the numbers elsewhere on this page.

Key implementation decisions (deviate from the original stub sketch, see each module's docstring for why):
- **Stage 0.5 (new)** `preprocessing/grid.py` — Calibrated products aren't map-projected, so Stage 0's AOI can't crop them by lat/lon directly. Uses the ground-control grid CSV ISRO ships alongside each product (`geometry/calibrated/.../*_g_grd_*.csv`, regular (line,sample)↔(lat,lon) points) to window a huge orbit strip (213595 lines here) down to ~17K lines before any pixel processing. Also shape-matches the REFERENCE crop to the source swath's actual footprint (reproject each corner's lat/lon into the reference's CRS via pyproj) instead of using the whole exported reference tile — a narrow push-broom strip barely overlaps a square AOI export otherwise.
- **Stage 1** `preprocessing/illumination.py` — DEM-based hillshade re-rendering isn't viable: the LRO reference is a pre-blended QuickMap mosaic with no single sun angle to re-target. Falls back to a Gabor-energy structure map, used only by the classical matcher — the learned matcher (LoFTR) runs on the plain tile instead.
- **Stage 2** `pyramid/coarse_to_fine.py` — builds a source pyramid and resamples the reference to match each level's GSD (skips levels needing an unreasonable reference resize), so matching happens at a shared physical scale. Originally written against a ~20x source/reference GSD gap (the old WAC reference); with the current NAC reference the gap is ~1.2x, so the finest level now survives near-native resolution — see "Reference data swap"'s performance-fix notes for what that required.
- **Stage 3 (blind fallback only)** `matching/classical.py` + `matching/crater.py`. LoFTR was removed from the MVP (the default `prior_guided` path never used it); a verified ONNX export of it is in git history at commit `b604266` for future work.
- **Stage 5** `geometry/robust_fit.py` — homography + `cv2.USAC_MAGSAC` only; DTM orthorectification (`geometry/orthorectify.py`) and sub-pixel refinement are still stubs.

**Known quality ceiling (investigated, not a bug)**: original real-data run got 5 inliers out of 51 candidate matches. Root-caused by isolating level 0's 32 high-confidence (≥0.5) LoFTR matches and fitting independently: homography RANSAC caps at 5-6/32 inliers from 1px up through 10px reprojection threshold, and swapping to affine (fewer DOF, should be more forgiving of noisy correspondences if the model were the problem) gives the *same* ceiling (4-6/32 even at 20px). That rules out "wrong transform model" or "threshold too strict" as the cause -- it means only ~5-6 of the 32 high-confidence matches are actually mutually geometrically consistent under any reasonable rigid-ish transform. The rest are locally-plausible LoFTR/ORB matches that don't hold up globally, consistent with the known failure mode of matching repetitive, self-similar cratered terrain (small craters/rocks look alike in many places). `reproj_threshold_px` was bumped 1.0→3.0 (1.0 was unrealistically strict for a ~68m/px coarse level and cost 1-2 legitimate inliers for no real precision gain) -- a small honest improvement, not a fix for the ceiling itself.

This ceiling held through the accuracy-improvement round below (still ~5 independent anchor regions) -- what actually moved it was swapping the reference data itself; see "Reference data swap" below, which supersedes most of this section's numbers.

## Problem-statement coverage — illumination / viewpoint / scale (session 3, supersedes older numbers)

User supplied six new OHRC passes (south polar, Sun 0-4 deg), six new TMC-2 strips (two RAW-level, four north-polar,
Sun 7-13 deg, nadir/fore/aft), a PRADAN script for IIRS cubes, and asked to solve all three difficulties of the
problem statement ("do the maximum best possible"). Everything below was measured; honest limits are listed at the end.

**Data placement.** `data/raw/chandrayaan2/{ohrc,tmc2,iirs}/<product>/` (zips unpacked; the duplicate
`ch2_ohr_..0724..(1).zip` is byte-identical and was skipped). IIRS: only 2 of the 5 cubes were fetched (the PRADAN session
cookie expired after an hour, the third file broke at 2.05/2.2 GB and the remaining two returned empty bodies) -> re-run the
script from a fresh login for the rest. References (all in `data/raw/lro_reference/`): WAC 100 m via
`scripts/fetch_wac_reference.py` (fixed a lon>180 bug: it subtracted 180, not 360); south-polar NAC mosaic via
`scripts/fetch_trek_polar_nac.py` (Moon Trek WMTS, only served to 4.18 m/px, 2.09 m for one layer; orientation verified on named
craters); LOLA 20 m DEM windows via `scripts/fetch_lola_dem_window.py` (COG range reads of PGDA's LDEM_80S). The equatorial WAC
mosaic is black at -85 deg, so it is useless for the south polar strips. North-polar strips have an LRO WAC reference (primary)
and a Chang'e-2 7 m reference (`*_ce2.yaml`, supplementary cross-check, *not* LRO). No north-polar LOLA DEM was downloaded
(PDS `LDEM_80N_20M`, 1.85 GB, is the source). Configs for everything: `algo/configs/` (`scripts/make_config.py` writes one from a
product's own grid).

**Product facts worth knowing.** OHRC usability: only 20260721 is lit end to end; 20260628 is lit for its first 42k lines,
20241115 for lines 42k-75k, 20260729 for 3.4 km only (Sun below the horizon), 20260724 is 95% dark, 20260728 is black (DN 1-2:
kept as the refusal example, config `ohrc_20260728`). `ch2_tmc_nrn/nra` are RAW level: no geometry grid, only label corners ->
`preprocessing.grid.corner_control_grid`. Label `pixel_resolution`/roll/pitch/altitude are now parsed (the footprint-based GSD
is wrong near the poles). OHRC passes are pitched up to 23 deg.

**What changed in the algorithm** (details and module map: `docs/architecture.md`):
1. *Illumination.* `matching/structure.py`: one zero-mean NCC (`joint_ncc`) over several representations of the same pixels
   (local-normalised intensity, gradient magnitude "edges", oriented-gradient channels "cfog", ...). The correlation
   surface is chosen per scene in two steps: a capture-stage *agreement vote* over (reference layer x representation)
   candidates, then a fine-stage *self-consistency* check (agreement alone cannot see an illumination-biased surface:
   the relit-DEM + image fusion was 2 px biased until this was added). A feature-pixel budget skips 6-channel cfog on huge crops.
   `illumination/relight.py` renders a DEM with the source's own Sun (cast shadows by horizon scan, polar-grid convergence
   handled) and `registration.relit` correlates the source against it as a second reference layer.
2. *Viewpoint.* `geometry/nonrigid.py` (thin-plate spline, adopted only if blocked cross-validation beats the plain homography),
   `geometry/parallax.py` (DEM x tan(emission angle), sign and applicability decided by the imagery, magnitude bounded by the
   label geometry), `geometry/model_fit.py`; the matcher refits this model between stages and resamples tiles through it
   (`_inverse_lattice`). Wide-search *rescue* (rotation x scale hypotheses, coarse, consensus + rival test) for a badly wrong prior.
3. *Scale.* One common ground resolution per stage (reduce the finer image), source decimated on read
   (`crop_source_to_aoi(decimation="auto")`), tile/search sizes follow the ground footprint, IIRS band-averaged and de-striped,
   affine-robust stage fit for narrow strips (homography RANSAC is degenerate on 250-px-wide strips: the first IIRS run failed on
   exactly this).
4. *Honesty.* Source-quality gate (shadow / Sun below horizon), stage consistency guard (a degenerate stage fit now fails the run
   instead of continuing into garbage; the first IIRS run showed this), per-run held-out error, "no reliable fit" in the app.
5. *Deliverables.* `registered.tif` (source resampled onto the reference grid, georeferenced), `tiepoints_geo.csv`,
   `transform.json` with the field lattice.
6. *Speed.* Features per stage once instead of per tile, tile loop on threads (`ALGO_THREADS`), OpenCV's NCC for single channels:
   Tycho 146 s -> ~80 s on a busy machine.

**Correction to an earlier claim.** The older text below says "a non-rigid warp would gain little". That was measured on the
MAGSAC *inliers*, i.e. on exactly the tiles a homography fits (selection bias). With all tiles and cross-validation the Tycho
strip's homography leaves a held-out error of 4-5.6 px (20-28 m) that a smooth field reduces to 1.3-2.1 px, and the field's
peak is ~16 px (80 m). The final model is therefore not a single homography whenever the field is adopted
(`metrics.nonrigid`); `transform.json` stores both.

**Headline measurements** (3 seeds/case, success = RMS < 1.5 px; full tables `docs/benchmark.md`): Sun azimuth difference — old intensity-only 100% to 60 deg, 0% from 90; representation vote 100% to 60, 67% at 90, 100% at 180 (bias/failure in between); DEM re-lit layer 100% at every difference 0-180 deg (0.01-0.37 px). Non-rigid distortion 6 px RMS: 3.4 px -> 0.35 px. DEM parallax 15 deg: 12.6 px -> 0.73 px (25 deg: 15 -> 2.1 px, still failing). Wrong starting guess 2.5 km: 100% with the rescue search, 0% without; rotation 10 deg 100% vs 33%. Scale ratios 1-20x (and source coarser 2-8x): 100%, <=0.07 px. All three combined at once: mostly failing (1.6-9 px) — the real limit. Real data (`docs/results.md`): OHRC 20260721 4.8 m RMS / 2.3 m held-out vs a 4.18 m mosaic; Tycho 4.4 m; TMC fore strip over rough terrain 262 m -> 72 m with DEM parallax+re-lit layer; LRO-WAC vs Chang'e-2 references of the same strip disagree by 0.1-0.3 km, i.e. at the references' own co-registration level.

**Measurements.** Synthetic ground truth (known transform): `docs/benchmark.md` (regenerate with
`python -m algo.benchmark.suites <suite>` then `python -m algo.benchmark.report`). Real data, no ground truth: `docs/results.md`
(`python scripts/run_all.py`, `python scripts/make_results_doc.py`), plus `scripts/cross_check.py` (same strip against two
independent references; wrong starting guesses).

**Limits, stated plainly.**
- No ground truth for real pairs: the real-data numbers are residuals, held-out errors and agreement between independent routes,
  not absolute accuracy. A reference mosaic's own error (NAC polar mosaic vs LOLA, WAC 100 m pixels) is in none of them.
- Without a DEM, illumination robustness degrades beyond ~60 deg Sun-azimuth difference (benchmark: gradient-based matching is
  biased by 4-5 px at 90 deg); with a DEM the re-lit layer restores sub-pixel accuracy in the synthetic scenes. The synthetic
  scenes use pure shading plus a synthetic albedo texture: a harder shading change than real, an easier albedo one.
- Parallax from a DEM needs the label's view angle; a heavily distorted coarse tile can only be bootstrapped from it. Labels are not
  trusted blindly: the sign/applicability is decided by the imagery.
- OHRC against a 4.18 m reference is limited by that reference's pixel; the 0.25 m detail is averaged away. A 1-2 m NAC reference
  (a 2.09 m layer exists for one pass) would be better where available.
- Only TMC-2/OHRC/IIRS strips with the references above were run; smooth mare with few craters correlates poorly and yields few tiles.

## Accuracy improvements

Four stages added after the first real run, in `algo/src/algo/{matching/crater.py, geometry/consistency.py, preprocessing/relief.py, geometry/refine.py}` (each module's own docstring has the full rationale; summary + honest results here). Grounded in a literature pass (crater-pattern matching for lunar/planetary terrain-relative navigation -- Christian, Derksen & Watkins 2021, arXiv:2009.01228; PSO-SIFT's pre-RANSAC consistency voting -- Ma et al. 2017, IEEE TGRS; RIFT/LGHD/CFOG/HOPC phase-congruency descriptors for illumination-robust multimodal matching, not yet implemented -- see "still open" below).

- **`matching/crater.py`** (new matcher, runs alongside LoFTR/ORB): detects candidate craters as the top-N brightest/darkest local intensity peaks per tile (`skimage.feature.peak_local_max`, capped count -- an absolute LoG-response threshold was tried first and proved wildly scale-dependent, finding thousands of "blobs" on one tile), then matches them between source and reference by the scale+rotation-invariant relative geometry of each blob's 4 nearest neighbours (a local "constellation signature", the same idea as star-pattern identification). Contributes real candidates (~20-30/level on the real run) without materially changing the final inlier count on its own.
- **`geometry/consistency.py`** (confidence boost, not a filter): scores every candidate match by how many *other* candidates agree with it on implied pairwise scale/rotation, and boosts confidence accordingly, so ANMS's per-cell ranking prefers globally-consistent matches. Originally written as a hard pre-RANSAC filter (PSO-SIFT's actual design) -- empirically regressed the real run from a well-tested 5-inlier fit to a *different*, degenerate 4-point fit (a homography has 8 DOF, so exactly 4 points fit with ~0 residual by construction, not a validated result). Converted to a soft boost once that was caught; MAGSAC still sees the full candidate pool so this stage alone can't starve it.
- **`preprocessing/relief.py`** (confidence boost, uses the real DTM): down-weights match confidence by `cos(slope)` sampled from the DTM at each match's ground location (unknown/out-of-coverage locations are left unchanged, not penalized) -- a cheap proxy for relief-induced parallax risk, since full orthorectification needs a sensor pointing model the Calibrated products don't expose (see `geometry/orthorectify.py`, still a stub).
- **`geometry/refine.py`** (sub-pixel refine + guided densification, seeded by the first MAGSAC pass's inliers): for each inlier, locates its true sub-pixel position via local NCC, then searches a small neighbourhood around each inlier (constrained by the current transform's prediction) for nearby correspondences the blind matchers missed. Two real bugs were found and fixed while verifying this against the actual data (not just trusting first-pass code): (1) comparing a native-source-resolution template directly against a native-reference-resolution search window without resampling -- a ~20x GSD mismatch, the same bug pyramid-matching exists to avoid, reintroduced here by skipping the pyramid; (2) indexing the small `reference_crop` array with `reference_xy`'s *absolute full-raster* pixel coordinates (correct for `preprocessing.relief`, which needs them for the raster's affine transform, but not a local array index) -- silently went out of bounds on every real inlier and made refinement a no-op until caught by instrumenting the real run, not by code review alone.

**Measured effect on the real Tycho run** (after fixing both bugs above): second-pass MAGSAC finds 13 inliers from 28 refined/densified candidates (up from 5/51), RMSE 1.7px at the ~68m/px coarse pyramid level. Verified this isn't a degenerate artifact (checked match_count > inlier_count so real outlier rejection is still happening, inspected `matches.csv` and the `visualize_run.py` overlay) -- but the honest characterization is that densification found 1-4 *corroborating* nearby points clustered around each of the same ~5 anchor regions the original run found, not 13 independently-distributed new anchors across the AOI. That's a real win for local robustness (the fit is less sensitive to any single point's noise) but not a resolution of the "only ~5 distinguishable regions" finding above -- reference_y was checked against source_y across the 13 points and is not monotonic along the swath, consistent with (not a new regression introduced by) the pre-existing diagnostic finding that this is a genuinely hard, noisy correspondence problem.

Still open, roughly in order of expected value: (1) a real phase-congruency/log-Gabor descriptor (RIFT or LGHD) in place of the classical matcher's current Gabor-energy + ORB, which the literature pass flagged as the standard approach for illumination-robust cross-sensor matching but wasn't implemented this round (bigger lift: needs a log-Gabor filter bank and a MIM-style descriptor, not a drop-in swap); (2) DTM orthorectification (`geometry/orthorectify.py`, still unimplemented) to remove relief-induced parallax outright rather than just down-weighting it.

## Reference data swap — the real lever

The WAC reference above was a QuickMap *screenshot* export (720×1244px PNG, 86 m/px) -- not a downloaded product, just a low-res web preview. At 86 m/px a 150m crater is 2 pixels; that's almost certainly why the "known quality ceiling" above existed at all, more than anything in "Accuracy improvements" could fix. Caught when the user noticed the reference was only ~1MB while source/DEM were multiple GB.

The fix: `data/raw/lro_reference/tycho/catalog/lroc-nacftmos-products.geojson` (gathered during the original QuickMap search, never used) already listed a real LROC NAC frame over Tycho. Rather than use that raw EDR directly (uncalibrated, not map-projected -- would need ISIS3/SPICE photogrammetric processing, a much bigger lift than anything else in this project), found and downloaded **`NAC_ROI_TYCHOCTRLOA_E430S3489_5M.TIF`** from `data.lroc.im-ldi.com`: a pre-built, pre-calibrated, map-projected **controlled NAC mosaic at 5.00 m/px**, almost matching the source's 4.2 m/px (vs. the old ~20x gap). AOI narrowed to this mosaic's own footprint (lon 348.0-349.8, lat -43.85 to -42.15) since the old AOI extended into WAC-only territory with no real reference data. The raw EDR (`data/raw/lro_reference/tycho/nac/M1127207575LE.IMG`) is kept on disk, set aside, in case photogrammetric processing is attempted later.

Wiring this in surfaced two more real bugs, both fixed:
- **Longitude wraparound** (`preprocessing/grid.py`'s `_project_wrap_safe`): this mosaic's Equirectangular CRS was built from *unwrapped* (always-increasing 0-360°) longitude, but `pyproj`'s CRS-to-CRS transform always normalizes longitude to (-180°, 180°] before projecting -- re-feeding it lon±360 makes no difference, it's collapsed internally regardless. The wrapped and unwrapped results land a full lunar circumference apart (~8,000 km). Fixed by detecting an Equirectangular (`+proj=eqc`) target CRS and computing the forward projection manually from the CRS's own parameters, then keeping whichever of that or PROJ's own result lands closer to the reference raster's own corner (so a CRS using the standard convention, like the old WAC's orthographic one, is unaffected). **The exact same bug was independently present in `preprocessing/relief.py`** (reverse direction: reference CRS → lon/lat → DEM lookup) and had made DTM relief-weighting a silent no-op since it was first written -- every lookup "missed" DEM coverage because -11.8° ≠ 348.2° to `rowcol()`. Fixed by normalizing with `% 360` there, matching the 0-360 convention used everywhere else in this codebase.
- **LoFTR OOM on a near-native-resolution tile** (`matching/learned.py`): with source/reference GSD nearly matched, the coarse-to-fine pyramid's finest level survives at close to full native resolution for the first time (previously the ~20x WAC-era gap meant only heavily-downsampled levels ever passed `MAX_REFERENCE_RESIZE`). A 10500×4000px tile into LoFTR's CNN backbone tried to allocate 2GB in one conv layer. Fixed with a tile-size guard (`_MAX_TILE_PIXELS`) that falls back to classical/crater matching, same mechanism as a missing checkpoint.
- **classical/crater matching became impractically slow** at that same near-native resolution (Gabor filtering + CLAHE + ORB, or blob detection, over a 42-million-pixel tile) -- two real runs blew through independent 30-minute background-task limits before this was caught (confirmed via an unbuffered, per-stage-timed diagnostic, `scripts/diag_match_stages.py`, after plain stdout buffering hid where time was going on the first attempt). Fixed with a shared `matching/_tiling.py` helper both matchers now use: downsample to a pixel budget before matching, rescale returned coordinates back to the tile's native space afterward. Tried raising the budget from 1M to 3M pixels expecting better results from more detail -- got *worse* ones (6 inliers vs 16 on the first MAGSAC pass, and 2x slower): more native resolution surfaces more fine-scale repetitive crater texture, i.e. more of the self-similarity problem, not free detail. Kept 1M.

**Result**: `inlier_count: 55, match_count: 90, inlier_ratio: 0.61, rmse: 1.93px` -- up from `inlier_count: 5, match_count: 51, inlier_ratio: 0.10, rmse: 0.72px` on the old WAC reference. The first MAGSAC pass alone (before `geometry/refine.py`'s densification) already found 16 independent inliers from 138 candidates, vs. 5 from 51 before -- a genuine increase in independently-found anchors, not just a densification artifact. `scripts/visualize_run.py`'s overlay confirms the reference crop now shows genuine crater-rim and boulder detail instead of blurred circles, and the ~9 distinct match clusters trace a plausible, roughly-consistent spatial arrangement between source and reference. Full pipeline run time: ~50s (was crashing or taking 30+ minutes before the fixes above). Not yet re-validated: whether this generalizes beyond this one AOI -- the NAC mosaic's narrow coverage (visible as black no-data regions in the overlay) means only a fraction of the original AOI is actually usable at this quality.

## Data on disk — Tycho AOI
- **Source** `data/raw/chandrayaan2/tmc2/ch2_tmc_ncn_20240124T0838058678_d_img_d18/` — Calibrated TMC-2 image, orbit 19674, 4.2 m/px. This is the exact companion image the Tycho DTM below was derived from (same orbit, same sun angle) — found by matching orbit/timestamp after two off-AOI (polar) downloads turned up no Tycho coverage via direct AOI search.
- **Reference** `data/raw/lro_reference/tycho/nac/NAC_ROI_TYCHOCTRLOA_E430S3489_5M.TIF` — real LROC controlled NAC mosaic, 5.00 m/px, Equirectangular (unwrapped-longitude, see above). Superseded `data/raw/lro_reference/tycho/wac_nac/` (86 m/px WAC screenshot export, kept on disk, no longer referenced by `configs/default.yaml`). Also on disk, set aside: `data/raw/lro_reference/tycho/nac/M1127207575LE.IMG`, the same area's raw NAC EDR (1.2 m/px native, uncalibrated).
- **DEM** `data/dem/tycho/` — real TMC-2 Derived DTM (10 m/px elevation).
- Scale ratio source/reference ≈ 1.2× (was ≈ 20× with the WAC reference).
- Set aside, not wired in (different AOIs, kept for reference): `data/raw/chandrayaan2/ohrc/` (Calibrated OHRC, South Pole) and `data/raw/chandrayaan2/tmc2/ch2_tmc_ncf_.../` (Calibrated TMC-2, North Pole). Both still useful — they validated `parse_pds4_label` generalizes across instruments with zero instrument-specific code.
- `data/raw/lro_reference/tycho/catalog/` — QuickMap product-search catalogs (GeoJSON, no pixel data) -- this is where the NAC mosaic lead came from; worth checking first for any future AOI before assuming a WAC-resolution screenshot is all that's available.

Lesson for next AOI: a Derived DTM's label records the `imaging_orbit_number` of the Calibrated image it was built from, so search by that orbit/timestamp rather than by AOI box alone. Also: check `lroc.im-ldi.com`'s curated RDR products (search "`<crater name>` NAC mosaic") for a pre-built, map-projected, high-res mosaic before settling for a WAC-resolution QuickMap export -- it's what actually fixed this project's registration quality, more than any amount of matcher tuning.

## Second AOI validation — Copernicus crater

Picked to check whether the Tycho result above generalizes, or was tuned to one AOI's specifics.

First attempt (south pole, lat 84.4-81.4°S) used LROC's own `NAC_ROI_EXPSITE2LOA` -- literally named "Chandrayaan 2 exploration site #2" by the LROC team, the strongest-looking lead available. **No CH2 Calibrated product was found there.** This contradicts the previous "catalog skews toward poles" lesson above (removed) -- that was inferred from only 2 prior downloads (one south-pole OHRC, one north-pole TMC-2) and didn't generalize; in practice most Calibrated TMC-2/OHRC coverage is near the equator/mid-latitudes, consistent with ordinary orbital imaging density. Switched to **Copernicus crater** (9.1-11.4°N, 339.6-340.8°E) instead, where a Calibrated TMC-2 swath (`ch2_tmc_ncf_20240623T0707183819_d_img_d18`, lat 17.05° to -20.89°, fully containing the Copernicus AOI) was readily available, paired with `NAC_ROI_COPERNICLOB_E103N3402_5M.TIF` (5.00 m/px controlled NAC mosaic of Copernicus's interior). New config: `algo/configs/copernicus.yaml` (`default.yaml`/Tycho left untouched); `dem.enabled: false` since there's no Derived DTM for this AOI.

First real run surfaced a genuine pipeline bug, not an AOI quirk: `pyramid/coarse_to_fine.py`'s `MAX_REFERENCE_RESIZE = 4.0` turned out to be a near-miss cutoff. Tycho's source GSD (4.2 m/px) keeps pyramid level 1's reference-resize ratio at 0.298 (comfortably under 4.0's reciprocal); Copernicus's source GSD for this swath is 5.9 m/px, pushing level 1's ratio to 0.212 -- just past the cutoff (true required headroom was 4.72x, not 4.0x). The AOI collapsed to a single near-native-resolution pyramid level with no coarse anchor, which starved LoFTR (tile-size guard) and forced classical/crater matching over a 42-68M pixel tile with no coarse-level corroboration: first MAGSAC pass found only 4 inliers from 39 candidates -- an exactly-minimal 4-point homography fit, the same "not meaningfully validated" pitfall flagged in "Known quality ceiling" above. `refine_and_densify` padded this to a flattering-looking 13/14 second-pass fit, but inspecting `matches.csv` showed those 14 points were really just 2 real anchors, densified.

Fixed by loosening `MAX_REFERENCE_RESIZE` to 5.0 -- still excludes genuinely unreasonable resizes (Copernicus's own level 2 would need 18.9x, still skipped) but recovers the near-miss level. Verified with `scripts/diag_match_stages.py` (made config-selectable, `python -u scripts/diag_match_stages.py <config_name>`, instead of hardcoded to `default.yaml`): Copernicus now builds 2 levels (5.9m, 23.5m -- same structure as Tycho's 4.2m/17.0m), candidate pool roughly doubled (39→80), and the first MAGSAC pass found 7 independent inliers from 80 candidates -- a real validated fit, not a 4-point degenerate one. Confirmed zero regression on Tycho (identical 2 levels, identical 16/138 first pass and 55/90 final numbers) and the full test suite (18/18 passing).

**Result**: `inlier_count: 16, match_count: 20, inlier_ratio: 0.80, rmse: 0.92px`. Smaller absolute counts than Tycho's (expected -- this mosaic's footprint is a fraction of Tycho's), but the real finding is qualitative: the same code, unmodified matching/geometry stages, on a different crater at a different latitude with a different source GSD, now produces a genuinely multi-level, validated fit. That's the actual generalization check this AOI was for -- the Tycho reference-data-swap fix wasn't a one-off tuned to that AOI's exact numbers, but the pyramid-level-selection cutoff was uncomfortably close to AOI-specific, which is now fixed for both.

## Desktop app — API server + Flutter UI

Wired the pipeline up to a real UI rather than CLI-only invocation, per user direction to prioritize usefulness over further matcher tuning for now. Two pieces, kept decoupled:

- **`algo/src/algo/api/server.py`** -- a small FastAPI server, run inside `algo`'s own venv (`python -m algo.api.server`, port 8000), that wraps the exact same `python -m algo.pipeline --config ...` CLI invocation already documented in the README rather than calling `pipeline.run()` in-process: each run is a subprocess (`cwd=algo/`, stdout+stderr to `data/results/<run_id>/run.log`), so a crash in one run can't take the server down, and a hung run doesn't block polling. `pipeline.py`'s `run()`/`main()` gained an optional `run_id`/`--run-id` passthrough (previously auto-generated inside `evaluate()`) so the server can pre-assign the run_id before launching the subprocess and return it immediately for polling. A background `threading.Thread` per run watches `proc.wait()` and writes a `meta.json` (`status`: running/done/error, `config`, timestamps, `stderr_tail` on failure) into the run's own output dir -- this is the only new persistent state; `metrics.json`/`matches.csv`/`transform.json` are unchanged, written by `evaluate()` as before. Endpoints: `GET /configs` (reads `configs/*.yaml`, one entry per AOI), `POST /runs`, `GET /runs` / `GET /runs/{id}` (merges `meta.json` + `metrics.json` + `transform.json`), `GET /runs/{id}/overlay.png`.
- **`algo/src/algo/api/overlay.py`** -- `scripts/visualize_run.py`'s side-by-side match plot, lifted out and made config-agnostic (that script was hardcoded to `configs/default.yaml`) so the server can render an overlay for a run from *any* config. Renders on first request, caches `overlay_matches.png` next to the run's other output files.
- **`desktop/`** -- Flutter desktop app (Windows/Linux/macOS), brutalist/instrument-panel design (thick square borders, no shadows, monospace data, one accent color). Home screen: config picker showing AOI bounds/source/reference/DEM status, an "EXECUTE REGISTRATION" button, and a live-polled run history table. Results screen: metric readouts, the match overlay image, the raw homography matrix, captured stderr on failure. Talks to `algo.api.server` over `http://127.0.0.1:8000` via the `http` package -- no Python embedded in the app itself.

Verified by actually starting the server and driving it end-to-end from curl (not just reading the code): `GET /health`, `GET /configs`, `POST /runs` with `copernicus.yaml`, polled `GET /runs/{id}` to completion (~4.5 min, matched the known-good `inlier_count: 16, match_count: 20, inlier_ratio: 0.8, rmse: 0.92` from the section above exactly), then `GET /runs/{id}/overlay.png` (200, valid 1680x1200 PNG), then `GET /runs` to confirm older pre-existing run directories without a `meta.json` degrade gracefully (`status: "unknown"`, `config: null`) rather than erroring.

**Not yet verified**: the Flutter/Dart code itself. Flutter isn't installed on this machine, so `lib/` was hand-written and carefully re-read for syntax, but never compiled. The one-time setup in `desktop/README.md` (`flutter create --platforms=windows,linux,macos .`, then `flutter pub get`) still needs to be run by hand before `flutter run -d windows` will work -- do that and fix whatever the analyzer/compiler flags before trusting the UI layer the way the backend has already been trusted.

## Desktop app — hardening the server lifecycle, real redesign

User feedback after the first pass above, worth preserving since the fixes are non-obvious:

- **The naive auto-start was silently killed a few seconds in.** The first `ServerLauncher` spawned the Python server via plain `Process.start(..., mode: detachedWithStdio)` from inside the running Flutter app. It worked for a few seconds (visibly: configs loaded) then died. Root cause: `flutter run` hosts the app inside a **Windows Job Object**, and a child process started the ordinary way -- even with Dart's "detached" mode -- stays a member of that job unless explicitly broken out, so it's killed the moment the job tears down (around when the debug session finishes attaching). Fixed by routing the spawn through `cmd /c start` on Windows specifically, which launches the target as a genuinely independent top-level process (a known, commonly-used workaround for this exact class of Electron/Flutter-on-Windows problem) -- this also opens a visible "Lunar Registration Server" console window, which is deliberate: it makes a crash visible instead of silently swallowed. Non-Windows platforms don't have this job-object issue, so they keep the simpler `detachedWithStdio` + log-file-capture path. Added `algo/start_server.bat` as a guaranteed-independent fallback (launched by Explorer, not by Flutter's process tree, so it can't be affected by this at all) for whenever auto-start still doesn't work.
- **"Does this architecture even make sense?"** -- user asked whether other real software does the local-GUI-talks-to-a-local-backend-over-HTTP pattern. Yes, and it's extremely common: Ollama's desktop app, LM Studio, Docker Desktop, Jellyfin/Plex, Jupyter, and various editor AI plugins (Tabnine etc.) all spawn/run a local server and have the UI (sometimes a different language/framework entirely) talk to it over localhost -- decouples the GUI framework from a heavy compute stack, lets the backend use whatever's actually suited to the work (FastAPI here, same as Jupyter's Kestrel/Python server model), and localhost HTTP is a clean, debuggable, swappable boundary. This project's Flutter-spawns-FastAPI-on-127.0.0.1:8000 design is squarely in that tradition, not a shortcut.
- **User's actual complaint wasn't the architecture, it was the UX**: server mechanics (banners, "server unreachable", flicker) were visible in the normal flow, and the connect sequence wasn't robust (sometimes just didn't connect). Restructured around a **splash-screen gate** (`lib/screens/splash_screen.dart`): it alone owns checking health -> launching if needed -> polling up to 45s, and the main app only ever mounts once the backend is confirmed reachable -- this is what kills the flicker, since the shell no longer renders through a live sequence of up/down states. Technical detail (paths searched, log location) is behind a collapsed "+ TECHNICAL DETAILS" toggle on the one genuine failure screen, not shown by default anywhere else. The sidebar's small "ONLINE" dot is the only acknowledgment in the normal UI that a backend exists at all.
- **Redesigned the app around a real "project" concept** instead of a flat "pick a YAML, hit execute" screen: `lib/widgets/sidebar_nav.dart` (persistent nav, PROJECTS/ABOUT) -> `lib/screens/projects_screen.dart` (grid of AOI projects, one card per `algo/configs/*.yaml`) -> `lib/screens/project_detail_screen.dart` (that project's AOI/source/reference/DEM info, a run button, and its own run history) -> `lib/screens/results_screen.dart` (unchanged). Added a real **New Project** flow (`lib/screens/new_project_screen.dart`) backed by a new `POST /configs` endpoint on the server: a form (lat/lon box, source instrument, source/reference/DEM paths) that validates server-side (paths must actually exist on disk, lat/lon ranges sane, no duplicate/unsafe names) and writes a real `configs/<name>.yaml` in the exact same shape as the hand-written ones -- verified live via curl (valid create, 409 on duplicate name, 400 on a nonexistent source path, confirmed the written YAML matches convention) before wiring the Dart side to it. Deliberately did *not* add a native file/folder picker (`file_selector` or similar) for the path fields -- typed paths instead -- since a new native-plugin dependency is a new class of risk I can't verify without the Flutter SDK installed here; noted as a low-risk fast-follow in `desktop/README.md` once the app is confirmed building.
- Old `lib/screens/home_screen.dart` (the flat config-picker-plus-global-history screen from the first pass) deleted, fully superseded by the above.

## Desktop app — real bug fix, readability, file picker

User feedback after the redesign above:

- **Real bug: opening a project with existing runs threw a widget error.** `ProjectDetailScreen` is pushed as its own route (`Navigator.push`), but its `build()` returned a bare `Padding(...)` with no `Scaffold`/`Material` ancestor of its own -- unlike content nested inside `AppShell`'s Scaffold (e.g. `ProjectsScreen`), a newly-pushed route doesn't inherit one. The run-history rows use `InkWell`, which throws "No Material widget found" without a Material ancestor. Didn't surface on first look because `_runs` starts empty and the empty-state branch has no `InkWell` -- it only hit once a project had at least one run, which the default Tycho project already did (20+ runs from earlier pipeline testing). Fixed by wrapping `ProjectDetailScreen`'s body in its own `Scaffold`, matching the pattern every other pushed-route screen (`ResultsScreen`, `NewProjectScreen`, `SplashScreen`) already used. Lesson: when a screen is reached via `Navigator.push`, check it has its own `Scaffold` even if it "looks like" a simple content screen -- `AppShell`'s Scaffold doesn't reach through a route push.
- **Readability**: the brutalist look used the monospace font for *all* UI text, including small letter-spaced uppercase labels (nav items, buttons, panel titles, hints) -- legible as a style statement, measurably harder to read at a glance. Rebalanced typography in `lib/theme/brutalist_theme.dart` into `monoStyle` (data only: numbers, coordinates, run IDs, paths, the homography matrix) vs `uiStyle`/`labelStyle`/`bodyStyle` (sans, Flutter's bundled default font, for everything read/scanned: nav, buttons, titles, hints, prose, error text). Kept the actual brutalist structure (thick square borders, no shadows, sharp corners, the accent color) untouched -- the complaint was about text legibility and interaction feedback, not the visual language itself, which the user said they liked.
- **Interactivity**: added a reusable `lib/widgets/hoverable.dart` (mouse-hover tracking) and wired it into project cards (border/background shift to accent on hover), sidebar nav items (subtle tint on hover, distinct from the accent-filled selected state), and `BrutButton` (now has hover *and* press states, not just press). Also fixed `ProjectDetailScreen`'s run-row `InkWell` to actually render its hover highlight now that the Material-ancestor bug above is fixed, plus gave it an explicit `hoverColor` matching the rest of the palette instead of Material's default.
- **Native file/folder picker for "New Project"**: previously deliberately skipped (typed paths only) to avoid an unverifiable native-plugin dependency; user asked for it explicitly despite that tradeoff, so added `file_selector` (Flutter-team-maintained, desktop-supported) + `path` (pure Dart, zero risk) to `pubspec.yaml`. Extracted the algo/.venv-finding logic that `ServerLauncher` already had into a shared `lib/services/algo_paths.dart` (`AlgoPaths.findAlgoDir()`), since the new picker needs the same thing for a different reason: converting an absolute OS-picked path into one relative to `algo/`, matching the convention every existing `configs/*.yaml` uses (falls back to the absolute path if `algo/` can't be located -- the server's path-join accepts that too, it just won't match house style). This really is new risk the backend/layout work wasn't: a native plugin needs its own platform registration, which `flutter pub get` handles automatically but can't be confirmed without the Flutter SDK installed here -- flagged plainly in `desktop/README.md` as the first thing to check if a build fails after this change.

## Desktop app — show the images, rethink what "run" means

Next round of user feedback, after confirming the Material-ancestor fix worked: "I literally have no idea what's going on." Four real issues, not cosmetic ones:

- **No visual context at all.** The app showed configs and numbers but never the actual imagery -- you couldn't see what AOI you were registering before running, or compare source vs. reference. Fixed with a genuinely new capability, not just UI: `algo/src/algo/api/preview.py` (`GET /configs/{name}/preview.png`) crops source+reference to the AOI straight from the config, independent of any run -- same crop logic the pipeline itself uses, so what you see *is* what gets registered. Pulled the shared crop-loading out of `overlay.py` into `algo/src/algo/api/_crops.py` (`load_aoi_crops`) so the two don't quietly diverge. Verified live: first request ~4.3s (real rasterio I/O against the actual Tycho TMC-2/NAC files), cached to `data/previews/<name>.png` after that (~0.07s), and visually confirmed the output actually shows the right crater imagery, not a placeholder. `ProjectDetailScreen` now shows this prominently (a 320px-tall panel above the AOI/Runs row, zoomable via `InteractiveViewer`) -- this is also the most direct answer to "why does re-running give the same thing": the two input images never change, so neither does the deterministic fit between them.
- **"Run Registration" was misleading.** The pipeline has no randomness exposed to the config -- confirmed from real history, two separate runs of the same `default.yaml` months apart produced bit-identical metrics. So a button that implies "run it again for a new result" was lying. Reframed `ProjectDetailScreen`'s action area (`_actionSection`): once a project has at least one completed run, "View latest results" becomes the primary action and "Re-run" drops to a secondary outline button with explicit copy explaining *why* it'll give the same answer. The run list highlights which row is the current latest-done one.
- **Readability regressed too far toward compact.** Bumped the typographic scale (`labelStyle` 11.5->12.5, `uiStyle` 14->15, `bodyStyle` 13->14, `monoStyle` 13->14) and spacing wholesale -- screen padding 28->36, `BrutPanel` padding 16->20, `BrutButton` padding 20x14->24x16, project-card grid tiles 320->360 with more gutter. Also made results more "contextable": `StatCard` gained an optional one-line `hint` (e.g. RMSE's card now says "lower is better, sub-pixel is ideal" directly on the card, not buried in docs), and the match overlay on the results screen is now a fixed 440px `InteractiveViewer` (zoomable) instead of unconstrained-and-small.
- **Nothing was copyable, and clickability wasn't always obvious.** Converted the data users would plausibly want to copy -- source/reference paths, run IDs, error/stderr text, the homography matrix -- to `SelectableText`. Deliberately *not* applied to the run-list rows themselves (those are click targets via `InkWell`; making their text independently selectable would fight the click-to-open gesture with a text-drag-to-select one). Audited cursor affordance: `_demToggle` in the new-project form was a bare `GestureDetector` with no hover cursor, now wrapped in `MouseRegion`; everything else already had one via `BrutButton`/`Hoverable`/`InkWell`'s own default.

## Desktop app — overflow, inline zoom fighting scroll, dead space, motion

Next round: "I literally have no idea what's going on" plus a real `RenderFlex overflowed` report and a UX complaint that turned out to be a real design flaw, not confusion.

- **Root cause of the overflow.** `ProjectDetailScreen` put the AOI info panel and the run list side-by-side in a `Row` wrapped in `Expanded`, which gives that `Row` a *tight* bounded height from whatever space was left under the header and preview banner. The info panel (not `fillHeight`) still had to fit inside that bounded height even though it wasn't the one asking to scroll -- once the re-run explanation paragraph plus six info rows exceeded the remaining space, it overflowed. Fixed structurally, not by nudging numbers: the whole screen below the header is now one `SingleChildScrollView`, so no section is ever squeezed into a height it doesn't ask for. This class of bug can't recur on this screen regardless of window size or run count.
- **Inline `InteractiveViewer` fought the page's own scroll.** Reported as "image displaying/zoom messes with scrolling." A pannable/zoomable image embedded directly in a scrollable page captures the same drag gesture a scroll would. Fixed by introducing `widgets/zoomable_image.dart`: a plain static `Image` (hover shows a zoom-cursor affordance) that opens a dedicated fullscreen `Dialog` on tap, and *only* the dialog contains `InteractiveViewer` -- nothing else there competes for the gesture. Replaces the inline zoom on both the project-detail preview and the results-screen match overlay.
- **"Why is there so much space under runs" was a real design flaw, not confusion.** A project is one fixed AOI, the pipeline is deterministic (see above), so most projects only ever have one run that matters -- yet the run list was a permanently-expanded, `fillHeight`-stretched table, mostly empty under 1-2 rows. Replaced it: `_latestRunCard` headlines whichever run is newest (running/done/error) with inline mini-metrics and the primary action; anything older collapses into a hand-rolled `_CollapsibleSection` (no package -- `AnimatedSize` + a rotating chevron) that starts closed and only renders at all when there's more than one run.
- **Layout rebalance.** Pulled the full-width 320px preview banner out of the top of the page (user: "don't like the image added at top," "previous one was clean") -- imagery is now a compact thumbnail living next to the AOI info panel, openable fullscreen like the overlay.
- **Motion.** Added a `PageTransitionsTheme` override (`_BrutPageTransitionsBuilder` in `brutalist_theme.dart`) so every `Navigator.push(MaterialPageRoute(...))` app-wide gets a fade+slide-up transition for free -- no call site changes. `BrutButton` now animates its hover/press state (`AnimatedScale` + `AnimatedContainer`) instead of snapping. `StatusPill`'s dot animates color changes. New `widgets/fade_in.dart` (`FadeSlideIn`) gives panels and project-grid cards a staggered fade-and-rise entrance instead of a flat cut.
- **On "clear the cache, maybe something's stuck":** there's no app-level cache to clear here (the only disk cache is `data/previews/*.png`, keyed correctly off config name, and it was already working). What likely *looked* like stale/cached state was the `RenderFlex` overflow itself -- a Flutter overflow renders a half-broken widget subtree (yellow/black striped bars) without crashing the whole app, which can look like leftover junk from a previous state. A full `flutter run -d windows` restart (not hot reload) after this fix, ideally after `flutter clean`, rules out any stale build artifact too.

## Copernicus result is WRONG (correction to "Second AOI validation")

The `inlier_count: 16, inlier_ratio: 0.80, rmse: 0.92px` Copernicus result above is a **degenerate
fit, not a validated one**; the "generalizes across AOIs" conclusion is retracted. Evidence
(`homography` in every Copernicus run's `transform.json`):
- Affine part has singular values (3.42, 0.03): it collapses the 4000x17000 source strip to a near-line. Expected is ~1.18 on both axes (5.9 m source / 5.0 m reference).
- The 16 "inliers" are ~5 distinct anchors repeated at 1-2 px offsets (densification), and they are mutually inconsistent: source y increases 4749 -> 12311 -> 14784 while matched reference y goes 10435 -> 4907 -> 10618.
- Independent check: the control-grid prior (the same lat/lon grid used for cropping, fit as a homography, singular values 1.18/0.99) predicts every match location to within 3,000-7,500 px; Tycho's matches agree with its prior to 40-55 px (a consistent ~200 m pointing offset, which is what a real fit looks like). So Tycho (55/90, rmse 1.93) is genuine; Copernicus is not.
- RMSE/inlier ratio can't catch this: a rank-deficient homography projects everything near a curve, so its reprojection error is small by construction.

Needed: reject ill-conditioned fits (affine singular-value ratio, scale vs. GSD ratio), dedupe near-identical inliers before counting, and use the control-grid prior both to reject matches far from it and to constrain matching. Not implemented yet.

## Desktop app — result visualization and reliability checks

User asked for a way to see the registration result (the fitted transform), then said the single
four-panel image was too small to judge, "looks plainly wrong", and inconvenient with everything in one
picture. The first version (`api/registration_view.py`, `/runs/{id}/registration.png`) is replaced by
the system below and deleted. The old `api/overlay.py` + `/overlay.png` endpoint still exist but the
UI no longer uses them (superseded by the numbered-match images).

- **`algo/geometry/analysis.py`** (tested in `tests/test_analysis.py`): transform conditioning (singular
  values of the homography's Jacobian *at the crop centre*; the top-left 2x2 block alone is
  origin-dependent for a homography), scale vs. GSD ratio, `distinct_anchors` (merges densified
  near-duplicate inliers), offsets vs. prior, and `health_checks`. Thresholds are heuristics calibrated
  on Tycho (good) and Copernicus (bad), not derived constants.
- **`preprocessing/grid.control_grid_prior_homography`**: the control-grid prior as a homography, an
  estimate independent of the matcher (Tycho matches sit 40-55 px from it, Copernicus 3,000-7,500).
- **`algo/api/visualization.py`**: `GET /runs/{id}/viz` (manifest: verdict, checks, params, image list)
  and `GET /runs/{id}/viz/{name}.png`. Ten separate images: footprint + warped grid vs. prior, false-colour
  blend, checkerboard, close-up patches, warped, reference, numbered matches on source and reference,
  residuals, prior agreement. Cached in the run's `viz/`; bump `VIZ_VERSION` to invalidate. First render
  ~6 s, then milliseconds. Verified on real runs through a live server: Tycho passes all 5 checks,
  Copernicus fails 4.
- **Reading the overlays honestly**: magenta/green fringes appear even on a correct fit, because the two
  sensors have different sun angles (shading flips polarity). Judge by whether the same ridges/craters sit in
  the same place (they do in Tycho's close-ups); this is not sub-pixel evidence.
- **Stale "running" runs (bug found while doing this)**: a server restart killed a running run's subprocess
  and its watcher thread, leaving `meta.json` at `running` forever (a Tycho run showed "running" for 225 min,
  so the project card looked busy). `_load_run` now settles any `running` run that this server process isn't
  watching and that started before it booted: `done` if `metrics.json` exists, else `error` ("interrupted").
- **Desktop UI**: results screen shows the reliability panel, then image tiles grouped as What the transform
  does / Matches / Diagnostics (480px tiles, two columns when wide), each with its own zoom dialog (~97% x 95%
  of the window, up to 16x, reset button). Project screen: past-runs section removed, imagery under the Latest
  run card, left column filled with AOI / source product / reference product / method / activity facts
  (`GET /configs/{name}/details`). `flutter analyze` is clean (info-level lints only). The Flutter SDK is at
  `C:\Users\LOQ\flutter`, so Dart changes can be analyzed now.

### Earlier pieces this builds on

- **`algo/src/algo/geometry/warp.py`** (new, pure function, tested in `tests/test_warp.py`):
  warps `source_crop` into `reference_crop`'s own local pixel frame using the run's fitted
  homography. The one real subtlety (same one `geometry/refine.py` and `api/overlay.py` already
  had to handle, see those sections above): `transform.json`'s homography maps source-crop pixels
  to the reference RASTER's *absolute* pixel coordinates, not `reference_crop`-local ones --
  `warp_source_into_reference_frame` left-multiplies by a translation that subtracts
  `reference_row_offset`/`reference_col_offset` before calling `cv2.warpPerspective`, so the result
  is directly indexable into `reference_crop`. Also returns an explicit `valid_mask` from warping a
  same-shape all-ones array alongside the source (`cv2.INTER_NEAREST`) -- warped pixel *values* can
  legitimately be zero, so "no source coverage here" can't be inferred from `warped == 0` the way a
  first draft of this assumed.
- **Correction on the first version:** an earlier draft called the Copernicus render a passing check
  ("expected narrow sliver"). That was wrong -- the user spotted it, and the view was doing its job by
  exposing a bad fit (see the Copernicus section above). Tycho's render is the real pass.

## Prior-guided dense registration (replaces blind matching as the default)

User: the results were "almost complete garbage", points in the match overlay were "like different places",
and there were far too few points. They were right; I had also overclaimed Tycho. Looking at it again: the old
Tycho fit's 9 distinct anchors all sat in one featureless plain (the global rotation was right, but one small
cluster cannot pin down a 17,000-line strip), and Copernicus was simply wrong.

**What the transform is.** A single 3x3 homography fitted (MAGSAC) to point matches; everything away from the
matches is extrapolation. So the fix is more, better-spread, and verified evidence, not tuning the one fit.

**New method** (`algo/matching/prior_guided.py`, `registration.mode: prior_guided`, now the default; set
`registration.mode: blind` for the old LoFTR/ORB/crater path, which is also the fallback when a product has no
usable control grid):
1. The control grid gives an independent source->reference prior (`preprocessing.grid.control_grid_prior_homography`).
2. A coarse capture stage (big search window, heavily downsampled) votes on the global shift by *consensus*
   (mode of tile shifts), not by an absolute correlation score (Copernicus correlation is only ~0.3).
3. Fine stages cover the whole overlap with tiles; each tile resamples the source into the reference frame
   through the current transform and finds its residual shift by NCC on a local-normalized image. The shifts
   are fitted with one homography (MAGSAC), then repeated with a smaller search window.
4. No fallback to blind matching on failure: "no reliable fit" is reported (`metrics.json` gets `failure`).
`metrics.json` also carries `registration_mode`, per-stage tile counts, and `rmse_m` (RMSE in metres; the UI
shows metres because "px" differs between a 5 m NAC and a 100 m WAC reference).

**Measured, through the real pipeline/server** (checks from `geometry/analysis.py`, all PASS):
| project | reference | tiles / agreeing | RMSE | offset from prior |
|---|---|---|---|---|
| Tycho (default) | NAC 5 m | 86 / 56 | 6.5 m | 31 px, spread 9 |
| Copernicus | NAC 5 m | 274 / 114 | 6.3 m | 173 px, spread 17 |
| strip_n45e10 | WAC 100 m | 88 / 81 | 47 m | 2 px |
| strip_n40e13 | WAC 100 m | 54 / 49 | 48 m | 7 px |
| strip_n47e09 | WAC 100 m | 78 / 75 | 44 m | 2 px |
Old blind method for comparison: Tycho 9 clustered anchors; Copernicus a degenerate fit (retracted above).
Copernicus's ~860 m offset was invisible to the blind matcher; the coarse stage finds it and ~500 tiles
independently agree on it (MAD 3 px in y), which is strong evidence even though the close-ups are hard to judge by
eye (source sun elevation 80 deg vs. a low-sun reference). `structure: edges` (gradient magnitude) fails on
Copernicus, hence `intensity` as default. Tycho's close-ups now show ridge lines coinciding to 1-3 px, and the
WAC strips show the same craters/ridges in the same places.

**Caveats, honestly:** there is no ground truth, only consistency evidence (many independent tiles agreeing, plus
visual overlays). WAC references are 100 m/px, so those fits are good to ~tens of metres, not metres. A homography
cannot model push-broom attitude jitter along a 100 km strip; the per-tile shift MAD (Tycho 8 px, Copernicus 16 px
in x) is the size of what it leaves on the table. The "agrees with the control-grid prior" check is now partly
circular because the method starts at the prior.

**New data** (user-downloaded TMC-2 strips in `data/ch2_tmc_*`, ~30-60N, 8-14E): projects `strip_n45e10`,
`strip_n40e13`, `strip_n47e09` (`algo/configs/`). References were built by `algo/scripts/fetch_wac_reference.py`
from NASA Moon Trek's public LRO WAC mosaic tiles (303 ppd), resampled to 100 m/px local-equirectangular GeoTIFFs
in `data/raw/lro_reference/<name>/wac/`. A NAC mosaic would be better wherever LROC publishes one.

**Runtime:** Tycho 42 s, Copernicus 131 s, WAC strips ~10 s (was ~4.5 min for Copernicus).

### Update: dense matching (supersedes the match counts in the table above)

User: happy with the results but wanted many more matches and a better-looking warped source.
- **Dense final stage** in `matching/prior_guided.py`: after the capture + two fit stages, a 128-px-tile,
  48-px-stride pass (WAC: 40/16) with a +-20 px search around the already-good transform. The correlation
  bar is *adaptive* (80% of the previous stage's median NCC, floor 0.2): Tycho correlates ~0.5, Copernicus
  ~0.3, so a fixed bar either starved Copernicus (204 matches at 0.35) or let noise through.
- Through the real server: Tycho 86 -> **2,439** matches (6.0 m RMSE, 42 s), Copernicus 274 -> **5,280**
  (6.2 m, 93 s), WAC strips 280-421 (47-58 m, ~4 s each). All five pass every reliability check.
- **Honesty:** dense tiles overlap, so match counts are not independent evidence. The "distinct anchors"
  check now counts one match per 64-px source cell (873 / 1,317 for Tycho / Copernicus).
- **Is a homography enough?** After the fit, the along-strip systematic residual (RMS of binned means) is
  0.5-1.0 px vs. a total RMS of 1.5-1.6 px, i.e. the leftover error is mostly noise, so a non-rigid warp
  would gain little at current precision. Revisit if a higher-resolution reference is used.
- Tried and dropped: averaging intensity-NCC and edge-NCC maps (`structure: both`) failed on both Tycho and
  Copernicus. `edges` alone fails on Copernicus; `intensity` stays the default.
- **Display:** raw TMC-2 DN is dark with sparse bright speckle (near-noon especially), which made the warped
  source "look nothing like the Moon". Source-derived images now use a 1-99.7 percentile stretch plus
  gamma 0.55 (`_SOURCE_GAMMA`, `VIZ_VERSION` 3). Near-noon sources still look flat and bright next to a low-sun
  reference; that is real, not a registration error (the bottom crater and the rim line up in both).
