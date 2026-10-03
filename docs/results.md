# Real-data results

Latest run of every project (`python scripts/run_all.py`). There is no ground truth for real pairs, so the numbers are consistency measures: **RMS** is the residual of the inlier tile matches against the fitted model; **held-out** is the same model's error on tiles it was *not* fitted to (blocked cross-validation); **cross-check** numbers (two independent references, wrong starting guesses) are in `data/results/cross_checks/`.

| project | source | reference | scale (ref/src) | matches (inliers) | RMS | held-out | representation | re-lit DEM | non-rigid field | time |
|---|---|---|---|---|---|---|---|---|---|---|
| copernicus_crater | TMC2 4.99 m | lroc_nac_roi_mosaic 5.0 m | 1.00x | 8128 (4769) | 7.6 m | 9.2 m | intensity | no | 12.6 m rms | 205 s |
| tycho_crater | TMC2 3.86 m | lroc_nac_roi_mosaic 5.0 m | 1.30x | 6358 (4496) | 4.4 m | 6.2 m | edges | no | 19.9 m rms | 110 s |
| iirs_s14e156 | IIRS 98.66 m | lroc_wac_mosaic 100.0 m | 1.01x | 665 (340) | 91.9 m | 86.2 m | intensity | no | not needed | 14 s |
| iirs_s31e155 | IIRS 97.19 m | lroc_wac_mosaic 100.0 m | 1.03x | 630 (491) | 115.1 m | 95.6 m | edges+intensity | no | not needed | 14 s |
| ohrc_20241115 | OHRC 0.24 m | lroc_nac_avg_mosaic_sp 4.2 m | 17.42x | 285 (248) | 3.5 m | 5.4 m | intensity+edges | yes | 8.0 m rms | 75 s |
| ohrc_20260628 | OHRC 0.29 m | lroc_nac_avg_mosaic_sp 4.2 m | 14.42x | **no reliable fit** | — | — | — | — | — | 58 s |
| ↳ | | | | _no consistent global shift (best agreement 0 tiles across 6 layer/representation candidate(s)) (the reference has data under only 54% of the strip's footprint); the reference and the source may share too little structure at this scale_ | | | | | | |
| ohrc_20260721 | OHRC 0.25 m | lroc_nac_avg_mosaic_sp 4.2 m | 16.72x | 786 (657) | 4.8 m | 2.3 m | intensity | yes | 149.6 m rms | 91 s |
| ohrc_20260728 | OHRC 0.23 m | lroc_nac_avg_mosaic_sp 4.2 m | 18.18x | **no reliable fit** | — | — | — | — | — | 34 s |
| ↳ | | | | _source has no usable contrast (mean DN 1.0, 1-99.5th percentile range 0.0): the strip is in shadow or unlit_ | | | | | | |
| ohrc_20260729 | OHRC 0.21 m | lroc_nac_avg_mosaic_sp 4.2 m | 19.91x | **no reliable fit** | — | — | — | — | — | 78 s |
| ↳ | | | | _stage 3: the 0 tile measurements are not consistent with one transform (too few agree); the prior may be wrong or the images too dissimilar_ | | | | | | |
| strip_n27w093 | TMC2 5.43 m | lroc_wac_mosaic 100.0 m | 18.42x | 402 (234) | 63.2 m | — | intensity+intensity@layer1 | yes | 183.4 m rms | 18 s |
| strip_n40e13 | TMC2 4.85 m | lroc_wac_mosaic 100.0 m | 20.62x | 258 (194) | 53.7 m | — | edges+intensity | no | not needed | 11 s |
| strip_n41e109 | TMC2 6.02 m | lroc_wac_mosaic 100.0 m | 16.61x | 372 (217) | 71.9 m | 82.3 m | intensity@layer1+edges | yes | 365.7 m rms | 15 s |
| strip_n45e10 | TMC2 5.62 m | lroc_wac_mosaic 100.0 m | 17.79x | 424 (403) | 35.8 m | 27.6 m | intensity+edges | no | 35.2 m rms | 12 s |
| strip_n47e09 | TMC2 5.62 m | lroc_wac_mosaic 100.0 m | 17.79x | 394 (363) | 44.1 m | 33.9 m | intensity+edges | no | not needed | 11 s |
| strip_n73e012 | TMC2 6.4 m | lroc_wac_mosaic 100.0 m | 15.62x | 412 (220) | 56.5 m | — | intensity@layer1+cfog@layer1 | yes | not needed | 13 s |
| strip_n73e012_ce2 | TMC2 6.4 m | chang_e2_ortho_mosaic 16.7 m | 2.61x | 1845 (1844) | 7.0 m | 9.6 m | intensity+edges | no | 10.4 m rms | 46 s |
| strip_n77e200 | TMC2 5.13 m | lroc_wac_mosaic 100.0 m | 19.49x | 284 (171) | 70.9 m | — | intensity@layer1+intensity | yes | not needed | 10 s |
| strip_n77e200_ce2 | TMC2 5.13 m | chang_e2_ortho_mosaic 16.7 m | 3.26x | 493 (399) | 17.1 m | 15.8 m | cfog | no | not needed | 55 s |
| strip_n79e249 | TMC2 5.71 m | lroc_wac_mosaic 100.0 m | 17.51x | 342 (125) | 65.6 m | — | intensity+edges | yes | not needed | 6 s |
| strip_n79e249_ce2 | TMC2 5.71 m | chang_e2_ortho_mosaic 16.7 m | 2.93x | 1371 (1316) | 8.3 m | 11.3 m | intensity | no | 15.4 m rms | 36 s |
| strip_n81e233 | TMC2 5.53 m | lroc_wac_mosaic 100.0 m | 18.08x | **no reliable fit** | — | — | — | — | — | 20 s |
| ↳ | | | | _no consistent global shift (best agreement 5 tiles across 6 layer/representation candidate(s)); the reference and the source may share too little structure at this scale_ | | | | | | |
| strip_n81e233_ce2 | TMC2 5.53 m | chang_e2_ortho_mosaic 16.7 m | 3.02x | 1710 (1082) | 24.3 m | 29.5 m | intensity+edges | no | 20.4 m rms | 35 s |
| tycho_relit | TMC2 3.86 m | lroc_nac_roi_mosaic 5.0 m | 1.30x | 6358 (4496) | 4.4 m | 6.2 m | edges | yes | 19.9 m rms | 150 s |

Held-out error is computed on cell-median residuals (a 48 px cell), so it is smoother than the per-tile RMS; read the two together. A reference mosaic's own pixel size (100 m for WAC) bounds what any of these can resolve.
