"""Benchmark suites: one per problem-statement difficulty, plus a combined one.

    python -m algo.benchmark.suites illumination --workers 6 --seeds 3

Variants compared (all run by the same `registration.register` the application uses):
  baseline   single intensity representation, homography only     (the pre-improvement behaviour)
  auto       representation chosen per scene by capture consensus (intensity vs gradient magnitude)
  auto+nr    auto + cross-validated non-rigid residual field
  relit      auto + DEM re-lit with the source's Sun as a second reference layer
"""

from __future__ import annotations

import argparse

from algo.benchmark.runner import sweep, summarize
from algo.benchmark.scenes import Spec

BASELINE = {"structure": "intensity", "nonrigid": False}
AUTO = {"structure": "auto", "nonrigid": False}
AUTO_NR = {"structure": "auto", "nonrigid": True}
RELIT = {"structure": "auto", "nonrigid": False, "relit_weight": 1.0}
RELIT_NR = {"structure": "auto", "nonrigid": True, "relit_weight": 1.0}
AUTO_NR_DEM = {"structure": "auto", "nonrigid": True, "use_dem": True}


def illumination(seeds: int):
    variants = {"baseline": BASELINE, "auto": AUTO, "relit": RELIT}
    cases = []
    for s in range(seeds):
        for daz in (0, 20, 40, 60, 90, 120, 150, 180):
            cases.append((Spec(content="dem", seed=s, src_size=1400, sun_ref=(300.0, 25.0), sun_src=((300.0 + daz) % 360, 25.0),
                               dem_blur_px=3.0, label=f"az{daz}"), variants))
        for el in (5, 12, 25, 45, 65, 80):
            cases.append((Spec(content="dem", seed=s, src_size=1400, sun_ref=(300.0, 25.0), sun_src=(300.0, float(el)),
                               dem_blur_px=3.0, label=f"el{el}"), variants))
    return cases


def viewpoint(seeds: int):
    variants = {"baseline": BASELINE, "auto": AUTO, "auto+nr": AUTO_NR, "auto+nr+dem": AUTO_NR_DEM}
    cases = []
    for s in range(seeds):
        for amp in (0.0, 1.5, 3.0, 6.0):
            cases.append((Spec(content="nac", seed=s, src_size=1400, field_amp_px=amp, label=f"field{amp}"), variants))
        for amp in (1.0, 2.5):
            cases.append((Spec(content="nac", seed=s, src_size=1400, jitter_amp_px=amp, label=f"jitter{amp}"), variants))
        for view in (5.0, 15.0, 25.0):
            cases.append((Spec(content="nac", seed=s, src_size=1400, parallax_view_deg=view, label=f"parallax{view:.0f}deg"), variants))
        for rot, persp in ((3.0, 0.0), (0.0, 0.15), (10.0, 0.1)):
            cases.append((Spec(content="nac", seed=s, src_size=1400, rotation_deg=rot, perspective=persp, label=f"rot{rot}_persp{persp}"), variants))
    return cases


def prior(seeds: int):
    variants = {"baseline": BASELINE, "auto": AUTO, "auto, no rescue": {**AUTO, "rescue": False}}
    cases = []
    for s in range(seeds):
        for shift in (30, 100, 250, 500, 900):
            cases.append((Spec(content="nac", seed=s, src_size=1400, prior_shift_px=float(shift), label=f"shift{shift}px"), variants))
        for rot in (1.0, 3.0, 6.0, 10.0):
            cases.append((Spec(content="nac", seed=s, src_size=1400, prior_rot_deg=rot, label=f"rot{rot}deg"), variants))
        for sc in (0.03, 0.08, 0.15, 0.25):
            cases.append((Spec(content="nac", seed=s, src_size=1400, prior_scale_err=sc, label=f"scale{sc}"), variants))
    return cases


def scale(seeds: int):
    variants = {"baseline": BASELINE, "auto": AUTO}
    cases = []
    for s in range(seeds):
        for k in (1.0, 2.0, 4.0, 8.0, 20.0):
            cases.append((Spec(content="nac", seed=s, src_size=2200 if k >= 8 else 1400, k_ref=k, prior_shift_px=max(2.0, 60.0 / k),
                               scene="copernicus" if k >= 20 else "tycho", label=f"ref_coarser_x{k:g}"), variants))
        for k in (2.0, 4.0, 8.0):
            cases.append((Spec(content="nac", seed=s, src_size=700, k_src=k, prior_shift_px=40.0,
                               scene="copernicus" if k >= 8 else "tycho", label=f"src_coarser_x{k:g}"), variants))
    return cases


def combined(seeds: int):
    """All three difficulties at once, in three strengths, on the DEM-rendered Tycho terrain: a Sun-azimuth change, a smooth
    non-rigid distortion, scan-line jitter and DEM-driven off-nadir parallax (label view angle passed to the DEM variants)."""
    variants = {"baseline": BASELINE, "auto": AUTO, "auto+nr": AUTO_NR, "relit+nr": RELIT_NR,
                "relit+nr+dem": {**RELIT_NR, "use_dem": True}}
    cases = []
    for s in range(seeds):
        cases.append((Spec(content="dem", seed=s, src_size=1400, sun_ref=(300.0, 25.0), sun_src=(0.0, 25.0), dem_blur_px=3.0,
                           field_amp_px=2.0, jitter_amp_px=1.0, parallax_view_deg=8.0, prior_shift_px=40.0, label="moderate"), variants))
        cases.append((Spec(content="dem", seed=s, src_size=1400, sun_ref=(300.0, 25.0), sun_src=(60.0, 25.0), dem_blur_px=3.0,
                           field_amp_px=3.0, jitter_amp_px=1.5, parallax_view_deg=14.0, prior_shift_px=60.0, label="strong"), variants))
        cases.append((Spec(content="dem", seed=s, src_size=1400, sun_ref=(300.0, 25.0), sun_src=(60.0, 6.0), dem_blur_px=3.0,
                           field_amp_px=3.0, parallax_view_deg=14.0, prior_shift_px=80.0, label="extreme_low_sun"), variants))
    return cases


SUITES = {"illumination": illumination, "viewpoint": viewpoint, "prior": prior, "scale": scale, "combined": combined}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("suite", choices=sorted(SUITES))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()
    rows = sweep(SUITES[args.suite](args.seeds), workers=args.workers, name=args.suite)
    print()
    print(summarize(rows, "label"))


if __name__ == "__main__":
    main()
