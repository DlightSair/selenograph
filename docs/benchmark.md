# Synthetic ground-truth benchmark

Every number below is measured against a *known* transform (see `algo/benchmark/`). A case counts as a success when its RMS error over the whole source frame is under 1.5 reference pixels. Errors are medians over seeds, in reference pixels (5 m for the NAC-class scenes, 20-100 m when the reference is block-averaged).

Variants: **baseline** — intensity correlation, homography only (behaviour before these improvements); **auto** — representation chosen per scene by capture consensus; **auto+nr** — auto + cross-validated non-rigid field; **auto+nr+dem** — auto + non-rigid field + DEM parallax model; **relit** — auto + DEM re-lit with the source's Sun as a second reference layer; **relit+nr** — relit + non-rigid field; **relit+nr+dem** — relit + non-rigid field + DEM parallax model

## All three at once (Sun azimuth + non-rigid + jitter + parallax)

| case | prior error (px) | baseline | auto | auto+nr | relit+nr | relit+nr+dem |
|---|---|---|---|---|---|---|
| moderate | 42 | 0% · 2.27 px | 0% · 2.36 px | 33% · 1.75 px | 33% · 1.61 px | 33% · 1.61 px |
| strong | 63 | 0% · 7.55 px | 0% · 8.76 px | 0% · 5.78 px | 0% · 8.84 px | 33% · 3.11 px |
| extreme_low_sun | 79 | 0% · 5.97 px | 0% · 6.22 px | 0% · 5.55 px | 0% · 7.72 px | 0% · 7.72 px |

## Illumination variation

| case | prior error (px) | baseline | auto | relit |
|---|---|---|---|---|
| az0 | 60 | 100% · 0.00 px | 100% · 0.01 px | 100% · 0.01 px |
| az20 | 60 | 100% · 0.08 px | 100% · 0.08 px | 100% · 0.07 px |
| az40 | 60 | 100% · 0.05 px | 100% · 0.04 px | 100% · 0.05 px |
| az60 | 60 | 100% · 0.28 px | 100% · 0.20 px | 100% · 0.08 px |
| az90 | 60 | 0% · 4.11 px | 67% · 1.35 px | 100% · 0.27 px |
| az120 | 60 | 0% · 5.13 px | 33% · 4.22 px | 100% · 0.19 px |
| az150 | 60 | 0% · 5.66 px | 67% · 0.26 px | 100% · 0.29 px |
| az180 | 60 | 0% · 6.10 px | 100% · 0.25 px | 100% · 0.37 px |
| el5 | 60 | 100% · 0.12 px | 100% · 0.13 px | 100% · 0.23 px |
| el12 | 60 | 100% · 0.07 px | 100% · 0.08 px | 100% · 0.15 px |
| el25 | 60 | 100% · 0.00 px | 100% · 0.01 px | 100% · 0.01 px |
| el45 | 60 | 100% · 0.06 px | 100% · 0.04 px | 100% · 0.03 px |
| el65 | 60 | 100% · 0.06 px | 100% · 0.05 px | 100% · 0.05 px |
| el80 | 60 | 100% · 0.05 px | 100% · 0.04 px | 100% · 0.04 px |

## Viewpoint / pointing error of the starting guess

| case | prior error (px) | baseline | auto | auto, no rescue | build |
|---|---|---|---|---|---|
| shift30px | 31 | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px | 0% · fail |
| shift100px | 100 | 100% · 0.03 px | 100% · 0.02 px | 100% · 0.02 px | 0% · fail |
| shift250px | 250 | 100% · 0.02 px | 100% · 0.02 px | 100% · 0.02 px | 0% · fail |
| shift500px | 500 | 100% · 0.06 px | 100% · 0.05 px | 0% · fail | 0% · fail |
| shift900px | — | 0% · fail | 0% · fail | 0% · fail | 0% · fail |
| rot1.0deg | 61 | 100% · 0.03 px | 100% · 0.03 px | 100% · 0.03 px | 0% · fail |
| rot3.0deg | 66 | 100% · 0.04 px | 100% · 0.03 px | 100% · 0.03 px | 0% · fail |
| rot6.0deg | 80 | 100% · 0.08 px | 100% · 0.02 px | 100% · 0.02 px | 0% · fail |
| rot10.0deg | 106 | 100% · 0.06 px | 100% · 0.05 px | 33% · 0.03 px | 0% · fail |
| scale0.03 | 62 | 100% · 0.04 px | 100% · 0.03 px | 100% · 0.03 px | 0% · fail |
| scale0.08 | 72 | 100% · 0.04 px | 100% · 0.06 px | 100% · 0.06 px | 0% · fail |
| scale0.15 | 96 | 67% · 0.04 px | 67% · 0.03 px | 0% · fail | 0% · fail |
| scale0.25 | 139 | 0% · fail | 33% · 0.02 px | 33% · 0.02 px | 0% · fail |

## Scale variation

| case | prior error (px) | baseline | auto |
|---|---|---|---|
| ref_coarser_x1 | 60 | 100% · 0.02 px | 100% · 0.01 px |
| ref_coarser_x2 | 30 | 100% · 0.01 px | 100% · 0.01 px |
| ref_coarser_x4 | 15 | 100% · 0.06 px | 100% · 0.04 px |
| ref_coarser_x8 | 8 | 100% · 0.03 px | 100% · 0.02 px |
| ref_coarser_x20 | 3 | 100% · 0.06 px | 100% · 0.05 px |
| src_coarser_x2 | 41 | 100% · 0.01 px | 100% · 0.01 px |
| src_coarser_x4 | 42 | 100% · 0.02 px | 100% · 0.02 px |
| src_coarser_x8 | 48 | 100% · 0.07 px | 100% · 0.07 px |

## Viewpoint variation (non-rigid, parallax)

| case | prior error (px) | baseline | auto | auto+nr | auto+nr+dem |
|---|---|---|---|---|---|
| field0.0 | 60 | 100% · 0.02 px | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px |
| field1.5 | 60 | 100% · 0.73 px | 100% · 0.73 px | 100% · 0.08 px | 100% · 0.08 px |
| field3.0 | 61 | 33% · 1.54 px | 33% · 1.55 px | 100% · 0.11 px | 100% · 0.11 px |
| field6.0 | 61 | 0% · 3.44 px | 0% · 3.86 px | 100% · 0.35 px | 100% · 0.35 px |
| jitter1.0 | 61 | 100% · 1.12 px | 100% · 1.12 px | 100% · 0.39 px | 100% · 0.39 px |
| jitter2.5 | 63 | 0% · 3.86 px | 0% · 3.54 px | 33% · 1.96 px | 33% · 1.96 px |
| parallax5deg | 60 | 33% · 4.15 px | 33% · 3.93 px | 33% · 2.99 px | 67% · 0.46 px |
| parallax15deg | 60 | 0% · 12.63 px | 0% · 12.72 px | 0% · 9.72 px | 100% · 0.73 px |
| parallax25deg | 59 | 0% · 15.37 px | 0% · 24.94 px | 0% · 26.33 px | 0% · 2.05 px |
| rot3.0_persp0.0 | 60 | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px |
| rot0.0_persp0.15 | 61 | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px |
| rot10.0_persp0.1 | 60 | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px | 100% · 0.01 px |
