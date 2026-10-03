"""One entry point for "register this source crop to this reference crop given a prior".

Shared by the pipeline and the synthetic benchmark, so the accuracy numbers the
benchmark reports are produced by exactly the code the application runs:

  1. dense prior-guided tile matching       (matching.prior_guided)
  2. robust homography over all tile shifts (MAGSAC, loose threshold)
  3. terrain parallax from a DEM, if one is given (geometry.parallax): the closed-form part of the
     viewpoint problem, two fitted coefficients
  4. smooth non-rigid residual field        (geometry.nonrigid; adopted only if blocked
                                              cross-validation shows it predicts held-out
                                              tiles better than the homography)
  5. re-selection of inliers against the *full* model, so parallax residuals
     that a rigid fit would have thrown away as outliers are kept
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from algo.geometry.analysis import apply_homography
from algo.geometry.model_fit import fit_full_model
from algo.geometry.nonrigid import NonRigidModel
from algo.matching.match import Match
from algo.matching.prior_guided import SourcePyramid, match_prior_guided


@dataclass
class RegistrationResult:
    matches: list[Match] = field(default_factory=list)  # every tile measurement
    inliers: list[Match] = field(default_factory=list)  # consistent with the final model
    model: NonRigidModel | None = None
    rmse_px: float | None = None  # inlier residual vs the full model, reference px
    info: dict = field(default_factory=dict)

    @property
    def homography(self) -> np.ndarray | None:
        return None if self.model is None else self.model.H

    @property
    def ok(self) -> bool:
        return self.model is not None and len(self.inliers) >= 4


def _source_size(source) -> tuple[float, float]:
    if isinstance(source, SourcePyramid):
        return source.full_size()
    h, w = np.asarray(source).shape[:2]
    return float(w), float(h)


def register(
    source,
    reference_crop,
    H_prior_local: np.ndarray,
    reference_gsd: float,
    cfg: dict | None = None,
    dem: np.ndarray | None = None,
    expected_view: tuple[float, float] | None = None,
) -> RegistrationResult:
    """`source`: ndarray or SourcePyramid; `H_prior_local` maps full-resolution source-crop
    pixels to `reference_crop` pixels. Everything returned is in those same two frames.
    `dem` (optional): heights on the reference crop grid, enabling the parallax model;
    `expected_view`: (|tan along-track|, |tan cross-track|) from the label, for the consistency check."""
    cfg = cfg or {}
    matches, info = match_prior_guided(source, reference_crop, H_prior_local, reference_gsd, cfg, dem=dem, expected_view=expected_view)
    result = RegistrationResult(matches=matches, info=info)
    if not matches:
        return result

    # fit threshold (reference px): tile shifts are measured to a fraction of a pixel
    thr = float(cfg.get("fit_threshold_px", 1.0 if reference_gsd > 20 else 2.0))
    loose = float(cfg.get("loose_threshold_px", max(3.0, 2 * thr)))
    src = np.array([m.source_xy for m in matches], dtype=np.float64)
    ref = np.array([m.reference_xy for m in matches], dtype=np.float64)
    conf = np.array([m.confidence for m in matches], dtype=np.float64)

    Hn = np.asarray(info["final_homography"], dtype=np.float64) if info.get("final_homography") else None
    if Hn is None:
        result.info["failed"] = "no homography fits the tile measurements"
        return result
    last = (info.get("stages") or [{}])[-1]
    last_tile_ref_px = float(last.get("tile", 0) * last.get("down", 1))
    resid0 = np.hypot(*(apply_homography(Hn, src) - ref).T)
    scale0 = 1.4826 * float(np.median(np.abs(resid0 - np.median(resid0))))  # robust spread of the tile residuals
    loose = float(np.clip(max(loose, 3.0 * scale0), loose, 4.0 * loose))
    keep = resid0 < loose

    model, keep = fit_full_model(
        src, ref, conf, keep, reference_gsd, _source_size(source), dem=dem, expected_view=expected_view,
        use_nonrigid=bool(cfg.get("nonrigid", True)), use_parallax=bool(cfg.get("parallax", True)),
        cell=float(cfg.get("nonrigid_cell_px", 48.0)), thr_base=thr, loose=loose, seed_H=Hn,
        dem_smooth_px=float(cfg.get("parallax_smooth_final", 0.3)) * last_tile_ref_px,
        alpha_tol=float(cfg.get("parallax_alpha_tol", 0.10)), parallax_prior=tuple(info["parallax_prior"]) if info.get("parallax_prior") else None,
    )
    if model is None:
        model = NonRigidModel(H=Hn)

    final_res = np.hypot(*(model.to_reference(src[keep]) - ref[keep]).T)
    result.model = model
    result.inliers = [m for m, k in zip(matches, keep) if k]
    result.rmse_px = float(np.sqrt(np.mean(final_res**2))) if len(final_res) else None
    result.info.update({"nonrigid": model.info, "fit_threshold_px": thr})
    return result
