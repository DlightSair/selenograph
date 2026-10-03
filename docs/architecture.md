# Architecture — registering Chandrayaan-2 imagery to LRO references

The problem statement names three obstacles. This is how each one is handled, where it lives in
`algo/src/algo/`, and how it was measured. Numbers: [benchmark.md](benchmark.md) (synthetic scenes with a *known*
answer) and [results.md](results.md) (every real project; no ground truth exists for real pairs).

```
 source strip  ─┐                                        ┌─> registered.tif  (source resampled onto the reference grid)
 (OHRC/TMC/IIRS)│   ┌─────────────────────────┐          ├─> transform.json  (homography + non-rigid field)
 label + grid ──┼──>│ prior: control grid or  │          ├─> tiepoints_geo.csv (lon/lat tie points)
                │   │ label corner coordinates│          └─> metrics.json, matches.csv, viz/*.png
 reference ─────┤   └────────────┬────────────┘
 (WAC / NAC /   │                v
  mosaic)       │   coarse capture (representation vote, wide-search rescue)
 DEM (LOLA/DTM) ┘                v
                     tile matching at one common ground resolution, 3-4 coarse-to-fine stages;
                     each stage re-fits [homography + DEM parallax + smooth field] and uses it as the next prior
                                 v
                     final fit, cross-validated, honest failure if nothing is consistent
```

## 1. Illumination variation

*Why it is hard.* Shading is the directional derivative of height along the Sun azimuth. Two images lit from
directions 90° apart show different derivatives of the same surface: shading flips polarity, shadows move, and an
edge's apparent position shifts with the lighting. Correlating brightness fails; so does anything that only looks at
local appearance once the geometry of light differs enough.

*What is done* (`matching/structure.py`, `matching/prior_guided.py`, `illumination/`):

1. **Several representations of the same pixels**, all correlated by one zero-mean NCC (`joint_ncc`): locally
   normalised intensity, gradient magnitude (`edges`, polarity-free), oriented-gradient channels (`cfog`), plus
   others kept for comparison (`orient`, `gmag`, `dogabs`, `logabs`).
2. **Self-consistency picks the correlation surface per scene, in two steps.** *(a) Capture vote*: every
   (reference layer x representation) candidate correlates the source on its own and gets the fraction of coarse tiles
   that agree on one global shift; the final surface averages the (at most two) best candidates within 8% of the leader,
   cheapest representation first. Averaging layers blindly is wrong: an image lit from another direction and a DEM re-lit
   with the source's Sun disagree, and the mean inherits the image's bias. *(b) Fine-stage check*: an agreement vote at coarse
   scale cannot see a *biased* surface (a few pixels of illumination-induced edge shift is below a coarse tile's tolerance),
   but fine tiles can — at the first fine stage every candidate is re-measured and the surface whose inlier residuals scatter
   least wins (the capture's choice is kept unless another is clearly better). Intensity is exact (0.02-0.1 px) while the Sun
   is within ~40 deg; gradient magnitude keeps finding the right peak up to 180 deg; cfog is the most precise when lighting is
   close. A stage whose tiles stop forming one transform retries the next-best candidates, and expensive surfaces
   (6-channel cfog on a 60 Mpx crop) are skipped by a feature-pixel budget.
3. **Physical re-lighting** (`illumination/relight.py`, `illumination/dem.py`). A DEM does not depend on the Sun, so
   render it with the *source's own* azimuth/elevation (Lommel-Seeliger/Lambert blend, horizon-scan cast shadows) on
   the reference grid and correlate the source against that as an extra reference layer. This is the only thing
   that removes the representation-independent bias (gradient edges are displaced by the lighting: 4-5 px at 90°
   azimuth in the benchmark). Polar grids rotate "north", so the azimuth is corrected by the meridian convergence.
   Sun elevation of 1-4° (polar OHRC) makes the image almost pure topography, where this matters most.
4. **Quality gate** (`_source_quality_failure`): a strip in permanent shadow or with the Sun below the horizon (DN 1-2)
   is refused with a plain message instead of being "registered".

*Limits.* Without a DEM the representation route degrades beyond ~60° azimuth difference (bias, then failure).
Re-lighting uses a constant albedo and a Lommel-Seeliger/Lambert photometric model; a 20 m LOLA DEM cannot reproduce
shading from sub-20 m relief, so the relit layer helps with kilometre-scale topography, and the image layer carries
the fine detail.

## 2. Viewpoint variation

*Why it is hard.* A homography is exact for a flat scene and a pin-hole camera. Chandrayaan-2's cameras are
push-broom: each scan line has its own attitude (platform jitter), and terrain relief displaces a point by
`height × tan(emission angle)` along the look direction relative to the (orthorectified) reference.

*What is done* (`geometry/`, `registration.py`):

1. **Homography** for shift/scale/rotation/perspective, seeded by the product's control grid; for RAW products without
   a grid (`ch2_tmc_nrn/nra`) from the label's corner coordinates interpolated in a stereographic plane
   (`preprocessing/grid.corner_control_grid`, median 0.04-1 km from the real grid on products that have both).
2. **Wide-search rescue** (`_rescue_capture`) when the prior is badly wrong: coarser working resolution and a
   rotation × scale hypothesis grid; a hypothesis is accepted only if many tiles agree *and* it clearly beats any
   rival placement.
3. **DEM parallax** (`geometry/parallax.py`): `d(p) = α·(h(p) − h₀)/gsd` along the source's line/sample axes, α =
   tan of the local emission angle (label pitch/roll/camera tilt, with the Moon's curvature). The label gives the
   magnitude; its *sign* and whether it applies at all are decided by the capture tiles. On OHRC 20260721 the 14° pitch
   predicts tan = 0.26 and the imagery confirmed it (fitted 0.24, negative sign); a free fit that contradicts the label
   (e.g. 0.3 on a nadir strip) is rejected. The coefficient is then
   regressed on tile-averaged heights within ±10% of the label value, but the applied model uses the sharp DEM.
4. **Smooth non-rigid field** (`geometry/nonrigid.py`): a thin-plate spline through binned tile residuals, adopted
   only if *spatially blocked cross-validation* says it predicts held-out tiles better than the plain model.
5. **Progressive prior.** Between stages the whole model is re-fitted and the next stage resamples its tile
   templates through it (`_inverse_lattice`), so a tile measures small residuals even when the true displacement is
   far larger than its search window.

*Limits.* A coarse tile spans kilometres, so heavy parallax distorts it internally and can only be bootstrapped from
the label-derived prior; without a DEM only the smooth field is available. The field is smooth by construction: fine
discontinuities (cliffs) are not modelled.

## 3. Scale variation

`prior_guided.match_prior_guided` works at **one common ground resolution per stage**: the finer image is
block-averaged to the coarser, never the other way round. A 0.25 m OHRC strip is reduced to its 4 m NAC reference
(×16), a 5 m TMC-2 strip to a 100 m WAC reference (×20), and a 98 m IIRS cube leaves a 5 m reference to be reduced.
Huge strips are block-averaged *on read* (`crop_source_to_aoi(decimation="auto")`), tile and search sizes follow the
ground footprint, and hyperspectral cubes are averaged over the solar-reflected bands (0.9-1.6 µm) and de-striped.
Narrow strips (IIRS, 250 px) use an affine-robust stage fit because homography RANSAC is degenerate on them.

## Evaluation

* `algo/benchmark/` builds scenes with an exactly known transform from the real Tycho NAC mosaic and TMC DTM and
  sweeps one difficulty at a time (Sun azimuth/elevation, starting-guess error, scale ratio, non-rigid distortion,
  jitter, parallax) over several algorithm variants — the *same* `registration.register` the application runs.
* `scripts/cross_check.py` tests real data without ground truth: the same strip against two independent
  references (LRO WAC vs Chang'e-2), and from deliberately wrong starting guesses.
* Every run carries reliability checks (conditioning, scale vs the GSD ratio, distinct anchors, agreement with the
  prior, residual), and a held-out error from cross-validation.

## Deliverables of a run

`registered.tif` (source resampled into the reference grid, georeferenced), `tiepoints_geo.csv`, `transform.json`
(homography plus the field on a lattice), `metrics.json`, `matches.csv`, and the visualization set rendered on demand
by `api/visualization.py` for the desktop app.

## Module map

| area | modules |
|---|---|
| geolocation, crops, I/O | `preprocessing/grid.py`, `preprocessing/metadata.py`, `api/_crops.py`, `utils/io.py`, `export.py` |
| matching | `matching/prior_guided.py`, `matching/structure.py` (legacy blind path: `learned.py`, `classical.py`, `crater.py`) |
| illumination | `illumination/relight.py`, `illumination/dem.py` |
| geometry | `geometry/model_fit.py`, `geometry/nonrigid.py`, `geometry/parallax.py`, `geometry/analysis.py`, `geometry/warp.py` |
| orchestration | `registration.py`, `pipeline.py` |
| evaluation | `evaluation/metrics.py`, `benchmark/*`, `scripts/cross_check.py`, `scripts/run_all.py` |
| API / UI | `api/server.py`, `api/visualization.py`, `desktop/` (Flutter) |
