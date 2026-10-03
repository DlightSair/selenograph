"""Plain-numbers diagnostics for a fitted transform -- the checks a person
would otherwise do by squinting at an overlay. RMSE and inlier ratio can't
catch a *degenerate* fit (a rank-deficient homography projects every point
near one curve, so its reprojection error is small by construction; see
CLAUDE.md's Copernicus correction), so these look at the transform's shape,
how many genuinely independent anchors back it, and whether it agrees with
the independent control-grid prior.

The pass/fail thresholds are heuristics calibrated on two real AOIs (one
known-good, one known-bad), not derived constants -- each check reports its
measured value so a borderline case can be judged by eye.
"""

from __future__ import annotations

import numpy as np

_DISTINCT_TOL_PX = 64.0  # source px; dense tiles overlap, so only matches this far apart count as independent
_MIN_CONDITION = 0.5  # sigma_min / sigma_max of the affine part
_SCALE_BAND = (0.67, 1.5)  # fitted geometric-mean scale / expected GSD ratio
_MIN_ANCHORS = 6
_MAX_PRIOR_MEDIAN_PX = 500.0
_MAX_PRIOR_SPREAD_PX = 100.0
# the same limits in metres when the reference pixel size is known (a pixel count means 2.5 km on a 5 m NAC mosaic and
# 50 km on a 100 m WAC mosaic): a control grid can be a few km off a polar pass, but a *scatter* of the offset
# (the spread) beyond a few hundred metres means the matches do not agree with each other
_MAX_PRIOR_MEDIAN_M = 8000.0
_MAX_PRIOR_SPREAD_M = 800.0


def decompose_transform(H: np.ndarray, at: tuple[float, float] = (0.0, 0.0)) -> dict:
    """Singular values, rotation and reflection of the homography's local
    linear part (its Jacobian) at source point `at`. For a pure affine map
    that is just the 2x2 block; for a homography it depends on where you
    look (raw coordinates with large offsets make the top-left block
    misleading), so callers pass the centre of the source crop."""
    H = np.asarray(H, dtype=np.float64)
    x, y = at
    w = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    projected = (H[:2, :2] @ np.array([x, y]) + H[:2, 2]) / w
    affine = (H[:2, :2] - np.outer(projected, H[2, :2])) / w
    u, s, vt = np.linalg.svd(affine)
    rotation = u @ vt
    return {
        "sigma_major": float(s[0]),
        "sigma_minor": float(s[1]),
        "condition": float(s[1] / s[0]) if s[0] > 0 else 0.0,
        "geometric_scale": float(np.sqrt(s[0] * s[1])),
        "rotation_deg": float(np.degrees(np.arctan2(rotation[1, 0], rotation[0, 0]))),
        "reflected": bool(np.linalg.det(affine) < 0),
    }


def local_scale(H: np.ndarray, x: float, y: float) -> float:
    """Area scale of the homography at (x, y): sqrt(|det J|) = sqrt(|det H| / |w|^3)."""
    H = np.asarray(H, dtype=np.float64)
    w = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    return float(np.sqrt(abs(np.linalg.det(H)) / max(abs(w) ** 3, 1e-18)))


def apply_homography(H: np.ndarray, points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homog = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(H, dtype=np.float64).T
    return homog[:, :2] / homog[:, 2:3]


def distinct_anchors(source_xy: np.ndarray, tol: float = _DISTINCT_TOL_PX) -> list[int]:
    """Indices of a subset of points with at most one per `tol`-px cell -- the 'independent
    anchors' behind a fit whose inlier list is padded with near-duplicate densified points.
    Cell hashing (not all-pairs) so thousands of dense tile matches stay cheap."""
    seen: set[tuple[int, int]] = set()
    kept: list[int] = []
    for i, (x, y) in enumerate(np.asarray(source_xy, dtype=np.float64)):
        cell = (int(x // tol), int(y // tol))
        if cell not in seen:
            seen.add(cell)
            kept.append(i)
    return kept


def prior_offsets(H_prior: np.ndarray, source_xy: np.ndarray, reference_xy: np.ndarray) -> np.ndarray:
    """(matched reference position) - (where the prior says it should be), per match."""
    return np.asarray(reference_xy, dtype=np.float64) - apply_homography(H_prior, source_xy)


def health_checks(
    H: np.ndarray,
    source_xy: np.ndarray,
    reference_xy: np.ndarray,
    rmse: float | None,
    expected_scale: float | None,
    H_prior: np.ndarray | None,
    center_xy: tuple[float, float] | None = None,
    reference_gsd: float | None = None,
) -> list[dict]:
    """Each check: {label, ok, detail}. `ok` is None when it couldn't be evaluated.
    `center_xy` is where to measure the transform's local shape (default: median inlier)."""
    if center_xy is None:
        center_xy = tuple(np.median(np.asarray(source_xy, dtype=np.float64), axis=0))
    d = decompose_transform(H, center_xy)
    anchors = distinct_anchors(source_xy)
    # A push-broom strip is stored in acquisition order, so it can legitimately be a mirror image of a north-up map;
    # what matters is that the fit does not flip the handedness the product's own geolocation grid already has.
    prior_reflected = decompose_transform(H_prior, center_xy)["reflected"] if H_prior is not None else False
    flipped = d["reflected"] != prior_reflected
    checks = [
        {
            "label": "Transform is well-conditioned",
            "ok": d["condition"] >= _MIN_CONDITION and not flipped,
            "detail": (
                f"axis scales {d['sigma_major']:.2f} and {d['sigma_minor']:.3f} (ratio {d['condition']:.2f}; "
                f"a real fit is close to 1)"
                + ("; flips the image relative to the control grid" if flipped else "; mirrors the image, as the control grid does" if d["reflected"] else "")
            ),
        }
    ]
    if expected_scale:
        ratio = d["geometric_scale"] / expected_scale
        checks.append({
            "label": "Scale matches the GSD ratio",
            "ok": _SCALE_BAND[0] <= ratio <= _SCALE_BAND[1],
            "detail": f"fitted scale {d['geometric_scale']:.2f} vs expected {expected_scale:.2f} (x{ratio:.2f})",
        })
    checks.append({
        "label": "Enough independent anchors",
        "ok": len(anchors) >= _MIN_ANCHORS,
        "detail": f"{len(anchors)} distinct locations behind {len(source_xy)} counted inliers",
    })
    if H_prior is not None and len(source_xy):
        offsets = prior_offsets(H_prior, source_xy, reference_xy)
        median = float(np.median(np.hypot(offsets[:, 0], offsets[:, 1])))
        spread = float(np.sqrt(np.mean(np.sum((offsets - offsets.mean(axis=0)) ** 2, axis=1))))
        if reference_gsd:
            ok = median * reference_gsd <= _MAX_PRIOR_MEDIAN_M and spread * reference_gsd <= _MAX_PRIOR_SPREAD_M
            detail = (f"median offset {median:.0f} px ({median * reference_gsd / 1000:.2f} km), offset spread {spread:.0f} px "
                      f"({spread * reference_gsd:.0f} m); a real fit has a steady offset: its spread stays small")
        else:
            ok = median <= _MAX_PRIOR_MEDIAN_PX and spread <= _MAX_PRIOR_SPREAD_PX
            detail = f"median offset {median:.0f} px, offset spread {spread:.0f} px (a real fit has a small, steady offset)"
        checks.append({"label": "Agrees with the control-grid prior", "ok": ok, "detail": detail})
    else:
        checks.append({"label": "Agrees with the control-grid prior", "ok": None, "detail": "prior unavailable"})
    if rmse is not None:
        checks.append({
            "label": "Low reprojection error",
            "ok": rmse < 3.0,
            "detail": f"RMSE {rmse:.2f} px (necessary, not sufficient: a collapsed fit also scores low)",
        })
    return checks
