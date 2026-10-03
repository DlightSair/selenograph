"""Fit the full source->reference model (homography + DEM parallax + non-rigid field) to a set of
tile correspondences. Used twice: by the matcher between coarse-to-fine stages (so the next stage
measures small residuals around the improved model instead of large ones around a bare homography),
and by `registration.register` for the final fit.
"""

from __future__ import annotations

import cv2
import numpy as np

from algo.geometry.analysis import apply_homography
from algo.geometry.nonrigid import NonRigidModel, fit_nonrigid
from algo.geometry.parallax import fit_parallax


def lsq_homography(src: np.ndarray, ref: np.ndarray) -> np.ndarray | None:
    H, _ = cv2.findHomography(src.astype(np.float32).reshape(-1, 1, 2), ref.astype(np.float32).reshape(-1, 1, 2), 0)
    return H


def fit_full_model(
    src: np.ndarray,
    ref: np.ndarray,
    conf: np.ndarray,
    keep: np.ndarray,
    reference_gsd: float,
    source_size: tuple[float, float],
    *,
    dem: np.ndarray | None = None,
    expected_view: tuple[float, float] | None = None,
    use_nonrigid: bool = True,
    use_parallax: bool = True,
    cell: float = 48.0,
    thr_base: float = 1.0,
    loose: float = 3.0,
    iterations: int = 3,
    seed_H: np.ndarray | None = None,
    dem_smooth_px: float = 0.0,
    parallax_prior: tuple[float, float] | None = None,
    alpha_tol: float = 0.10,
) -> tuple[NonRigidModel | None, np.ndarray]:
    """Iterate (fit on inliers, re-select inliers against the full model). `src`/`ref` are (N, 2) in the
    full-resolution source frame and the reference-crop frame; `keep` the initial inlier mask. Returns
    (model | None, final inlier mask). The inlier bar follows the spread of residuals the *full* model
    leaves: noisy imagery (IIRS vs WAC) cannot meet 1 px, a model that explains the distortion keeps it tight."""
    keep = keep.copy()
    model: NonRigidModel | None = None  # stays None when there is too little data to fit anything
    parallax = None
    sw, sh = source_size
    use_parallax = use_parallax and dem is not None
    for it in range(iterations):
        if keep.sum() < 8:
            break
        H = lsq_homography(src[keep], ref[keep])
        if H is None:
            break
        target = ref
        if use_parallax:
            if parallax is None or it == 0:
                parallax = fit_parallax(src[keep], ref[keep], H, dem, reference_gsd, (sw / 2, sh / 2), expected_view,
                                        dem_smooth_px=dem_smooth_px, alpha_prior=parallax_prior, alpha_tol=alpha_tol)
            if parallax is not None:
                target = ref - parallax.field(apply_homography(H, src))
                H_corr = lsq_homography(src[keep], target[keep])
                H = H if H_corr is None else H_corr
        if use_nonrigid:
            nr = fit_nonrigid(src[keep], target[keep], H, weights=conf[keep], cell=cell)
        else:
            nr = NonRigidModel(H=H)
        if parallax is None:
            model = nr
        else:
            tps, pf = nr.field_fn, parallax
            model = NonRigidModel(H=nr.H, field_fn=lambda q, pf=pf, tps=tps: pf.field(q) + (tps(q) if tps is not None else 0.0),
                                  info={**nr.info, "parallax": pf.info})
        resid = np.hypot(*(model.to_reference(src) - ref).T)
        spread = 1.4826 * float(np.median(np.abs(resid[keep] - np.median(resid[keep]))))
        thr = float(np.clip(3.0 * spread, thr_base, loose))
        new_keep = resid < thr
        if new_keep.sum() < 8:  # the tight threshold killed almost everything: fall back to the loose set
            new_keep = resid < loose
        if np.array_equal(new_keep, keep):
            break
        keep = new_keep
    return model, keep
