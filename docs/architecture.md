# Architecture — hybrid registration pipeline

Reference for the design behind `algo/`. Source image = Chandrayaan-2 (OHRC/TMC-2/IIRS). Reference image = LRO (WAC/NAC).

## Why hybrid (not pure classical, not pure deep learning)

- No public labeled Chandrayaan-2 <-> LRO correspondence dataset exists, so training/fine-tuning a cross-modal matcher from scratch is high-risk and slow. Pure DL also risks silent hallucinated matches in a judged demo.
- Pure classical feature matching (SIFT/ORB-class) degrades badly under sun-angle-driven illumination change and struggles past ~30-50x scale ratios without heavy manual pyramid engineering.
- Hybrid: physics-informed classical preprocessing collapses the illumination problem, a **pretrained** (not lunar-trained) deep dense matcher does the heavy appearance/viewpoint matching, and classical robust geometry delivers the auditable sub-pixel output and metrics.

## Pipeline stages (maps 1:1 to `algo/src/algo/`)

| Stage | Module | Purpose |
|---|---|---|
| 0. Metadata | `preprocessing/metadata.py` | Parse PDS labels (sun az/el, GSD, footprint) for both images; estimate expected scale ratio & rotation before any pixel work |
| 1. Illumination normalization | `preprocessing/illumination.py` | DEM-based hillshade relighting (SLDEM2015/LOLA or TMC-derived DTM) when a DEM is available; phase-congruency structure maps as fallback |
| 2. Coarse-to-fine alignment | `pyramid/coarse_to_fine.py` | Match at common coarse GSD first, refine transform level-by-level up to native resolution — handles the large scale gap |
| 3. Correspondence | `matching/classical.py`, `matching/learned.py` | Primary: pretrained dense matcher (e.g. LoFTR). Fallback/cross-check: illumination-robust classical detector (RIFT/phase-congruency) on low-confidence tiles |
| 4. Uniform distribution | `matching/` (ANMS step) | Grid-based adaptive non-max suppression so crater rims don't dominate matches over flat mare terrain |
| 5. Outlier rejection + fit | `geometry/robust_fit.py`, `geometry/orthorectify.py` | MAGSAC++/RANSAC; homography on flat terrain, DTM-based orthorectification near relief; sub-pixel refinement of inliers |
| 6. Evaluation | `evaluation/metrics.py` | RMSE of inlier residuals, inlier count/ratio, spatial-uniformity metric |

## Build order (hackathon time budget)

1. Metadata parsing + coarse-to-fine scaffold (Stage 0-2) — get something aligned end to end.
2. Classical matcher (RIFT/phase-congruency) + RANSAC (Stage 3 fallback + Stage 5) — demoable baseline.
3. Swap in pretrained LoFTR as primary matcher (Stage 3 primary) — biggest accuracy jump, no training needed.
4. DEM-based hillshade normalization (Stage 1) — add if time remains.
5. Uniform-distribution ANMS + evaluation metrics (Stage 4, 6) — cheap, and directly what's graded — don't skip.

## Reference vs source assignment

- **Reference (fixed)**: LRO WAC/NAC — independently controlled, already georeferenced.
- **Source (moving)**: Chandrayaan-2 OHRC/TMC-2/IIRS — geometrically transformed to align with the reference.
- Prefer the **Derived Ortho** PDS product type as reference-side ground truth when cross-checking, and **Calibrated** product type as the registration source (radiometrically corrected, geometry not yet corrected — i.e. the thing that actually needs registering).

## AOI recommendation

Primary: Tycho Crater (~43.3°S, 11.36°W) — mid-latitude, high geomorphic complexity, well-studied, multi-instrument coverage. Alternative: Aristarchus Plateau (~23.7°N, 47.4°W) — high albedo contrast + Vallis Schröteri.
