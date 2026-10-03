"""Terrain parallax from a DEM: the part of the viewpoint problem that has a closed form.

A camera looking `theta` degrees off nadir sees a point that stands `h` metres above the
datum displaced by h * tan(theta) along the look direction relative to where an orthorectified
reference (NAC/WAC mosaics are built against the LOLA DEM) puts it. The homography absorbs the
mean height; what is left is proportional to the *local* height, which a DEM provides:

    d(p) = alpha_along * (h(p) - h0) / gsd * u_along  +  alpha_cross * (h(p) - h0) / gsd * u_cross

with u_along / u_cross the source line / sample directions as they land in the reference frame
and alpha = tan(view angle). The two alphas are *fitted* (signs depend on viewing and flight
conventions) and then compared with what the label's roll/pitch/camera-tilt say they should
be -- agreement in sign and magnitude is independent evidence that the field is real parallax
and not a fit to noise. Anything the DEM does not explain is left to the smooth
non-rigid model (`geometry.nonrigid`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import map_coordinates

from algo.geometry.analysis import apply_homography


@dataclass
class ParallaxFit:
    alpha_along: float
    alpha_cross: float
    explained: float  # fraction of the homography-residual variance the DEM terms explain
    info: dict
    basis_along: object  # callables p (N,2) -> (N,2) displacement per unit alpha
    basis_cross: object

    def field(self, p: np.ndarray) -> np.ndarray:
        return self.alpha_along * self.basis_along(p) + self.alpha_cross * self.basis_cross(p)


def expected_view_tangents(meta) -> tuple[float, float]:
    """(|tan along-track|, |tan cross-track|) of the *emission angle at the ground* implied by the label:
    TMC-2 fore/aft cameras are tilted +-25 deg along track on top of the spacecraft pitch; roll is
    cross-track; OHRC is steered by pitch/roll alone. The Moon's curvature makes the local emission angle
    larger than the camera tilt: sin(e) = sin(tilt) * (R + altitude) / R (7% in tan at 25 deg / 100 km)."""
    cam = {"f": 25.0, "a": -25.0}.get(getattr(meta, "camera", None) or "", 0.0)
    pitch = (meta.pitch or 0.0) if meta is not None else 0.0
    roll = (meta.roll or 0.0) if meta is not None else 0.0
    alt = getattr(meta, "altitude_km", None) or 0.0
    k = (1737.4 + alt) / 1737.4

    def emission(tilt_deg: float) -> float:
        s = np.sin(np.radians(abs(tilt_deg))) * k
        return float(np.arcsin(min(s, 0.999)))

    return float(np.tan(emission(cam + pitch))), float(np.tan(emission(roll)))


def _axis_directions(H_local: np.ndarray, centre_xy: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Unit vectors (in reference px) of the source line (along-track) and sample (cross-track) axes."""
    x, y = centre_xy
    p0 = apply_homography(H_local, np.array([[x, y]]))[0]
    ex = apply_homography(H_local, np.array([[x + 1.0, y]]))[0] - p0
    ey = apply_homography(H_local, np.array([[x, y + 1.0]]))[0] - p0
    return ey / np.linalg.norm(ey), ex / np.linalg.norm(ex)


def parallax_basis(H_local: np.ndarray, dem: np.ndarray, reference_gsd: float, centre_xy: tuple[float, float],
                   dem_smooth_px: float = 0.0):
    """(basis_along, basis_cross): callables taking reference-frame points (N, 2) to the displacement (ref px)
    one unit of tan(view angle) would cause there, from the DEM height relative to its median."""
    finite = np.isfinite(dem)
    h0 = float(np.nanmedian(dem))
    filled = np.where(finite, dem, h0).astype(np.float32)
    if dem_smooth_px > 0.5:
        # a tile's correlation peak responds to the terrain it covers, not only its centre: use the DEM
        # averaged over the tile footprint (coarse tiles span kilometres of relief)
        import cv2

        filled = cv2.GaussianBlur(filled, (0, 0), float(dem_smooth_px))
    u_along, u_cross = _axis_directions(H_local, centre_xy)

    def height(q: np.ndarray) -> np.ndarray:
        return map_coordinates(filled, np.stack([q[:, 1], q[:, 0]]), order=1, mode="nearest") - h0

    def basis_along(q):
        return (height(np.asarray(q, dtype=np.float64).reshape(-1, 2)) / reference_gsd)[:, None] * u_along[None, :]

    def basis_cross(q):
        return (height(np.asarray(q, dtype=np.float64).reshape(-1, 2)) / reference_gsd)[:, None] * u_cross[None, :]

    return basis_along, basis_cross


def _consistent_with_label(coef: np.ndarray, expected: tuple[float, float]) -> bool:
    """Each fitted tangent must be within [0.5, 1.6] x the label's value (or tiny when the label says ~0)."""
    for fitted, label in ((abs(coef[2]), expected[0]), (abs(coef[3]), expected[1])):
        if label < 0.04:
            if fitted > 0.06:
                return False
        elif not (0.5 * label <= fitted <= 1.6 * label) and fitted > 0.04:
            return False
    return True


def fit_parallax(
    source_xy: np.ndarray,
    reference_xy: np.ndarray,
    H_local: np.ndarray,
    dem: np.ndarray,
    reference_gsd: float,
    centre_xy: tuple[float, float],
    expected: tuple[float, float] | None = None,
    min_explained: float = 0.15,
    min_alpha: float = 0.02,
    dem_smooth_px: float = 0.0,
    alpha_prior: tuple[float, float] | None = None,
    alpha_tol: float = 0.10,
) -> ParallaxFit | None:
    """Regress the homography residuals on the DEM-height basis fields. `dem` is on the reference
    crop grid (NaN where unknown). Returns None when the DEM covers too little or explains nothing.
    `dem_smooth_px` blurs the DEM to the scale of the tiles the correspondences came from.
    `alpha_prior` = (along, cross) signed tan(view) already validated against the imagery (see the matcher's
    label-parallax check): the regression is then only allowed to move each coefficient by +-`alpha_tol`
    (relative), because coarse tiles under-estimate it (a tile averages a displacement that varies inside it)."""
    src = np.asarray(source_xy, dtype=np.float64)
    ref = np.asarray(reference_xy, dtype=np.float64)
    p = apply_homography(H_local, src)
    resid = ref - p

    if np.isfinite(dem).mean() < 0.3:
        return None
    # the coefficients are regressed against the tile-averaged DEM, but the model that is *applied* is
    # pointwise: its basis must be the sharp DEM (blurring it would erase the local relief it predicts)
    fit_along, fit_cross = parallax_basis(H_local, dem, reference_gsd, centre_xy, dem_smooth_px)
    basis_along, basis_cross = parallax_basis(H_local, dem, reference_gsd, centre_xy, 0.0) if dem_smooth_px > 0.5 else (fit_along, fit_cross)

    Ba, Bc = fit_along(p), fit_cross(p)
    # stack the x and y components into one regression: resid = c + alpha_a*Ba + alpha_c*Bc
    n = len(p)
    A = np.zeros((2 * n, 4))
    A[:n, 0], A[n:, 1] = 1.0, 1.0
    A[:n, 2], A[n:, 2] = Ba[:, 0], Ba[:, 1]
    A[:n, 3], A[n:, 3] = Bc[:, 0], Bc[:, 1]
    y = np.concatenate([resid[:, 0], resid[:, 1]])
    keep = np.ones(2 * n, bool)
    coef = np.zeros(4)
    for _ in range(4):  # IRLS-style trimming of outlier tiles
        coef, *_ = np.linalg.lstsq(A[keep], y[keep], rcond=None)
        r = y - A @ coef
        mad = np.median(np.abs(r[keep] - np.median(r[keep]))) * 1.4826 + 1e-6
        keep = np.abs(r) < 3.0 * mad + 0.3
    after = float(np.var((y - A @ coef)[keep]) + 1e-12)
    centered = float(np.var(y[keep] - (A[keep][:, :2] @ coef[:2])) + 1e-12)  # translation-only baseline
    explained = max(0.0, 1.0 - after / centered)
    info = {
        "alpha_along": round(float(coef[2]), 4), "alpha_cross": round(float(coef[3]), 4),
        "explained_variance": round(explained, 3), "dem_relief_m": round(float(np.nanpercentile(dem, 98) - np.nanpercentile(dem, 2)), 1),
    }
    if expected is not None:
        info["expected_abs_alpha_along"] = round(float(expected[0]), 4)
        info["expected_abs_alpha_cross"] = round(float(expected[1]), 4)
    if alpha_prior is not None:
        for k, a0 in ((2, alpha_prior[0]), (3, alpha_prior[1])):
            lo, hi = sorted((a0 * (1 - alpha_tol), a0 * (1 + alpha_tol)))
            coef[k] = float(np.clip(coef[k], lo, hi)) if a0 != 0.0 else 0.0
        info.update({"alpha_along": round(float(coef[2]), 4), "alpha_cross": round(float(coef[3]), 4), "alpha_prior": [round(a, 4) for a in alpha_prior]})
    elif explained < min_explained or max(abs(coef[2]), abs(coef[3])) < min_alpha:
        return None  # nothing the DEM can explain (negligible coefficient): leave it to the smooth field
    elif expected is not None and not _consistent_with_label(coef, expected):
        # An unvalidated regression may only claim parallax the label's viewing geometry can explain: a nadir
        # strip (label tan ~ 0) whose heights "explain" 0.3 of a tangent is picking up something else
        # (illumination-dependent edge shifts, reference artefacts) that merely correlates with relief.
        info["rejected"] = "fitted coefficient inconsistent with the label's viewing geometry"
        return None
    return ParallaxFit(float(coef[2]), float(coef[3]), explained, info, basis_along, basis_cross)
