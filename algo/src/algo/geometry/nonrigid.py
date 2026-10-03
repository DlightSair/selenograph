"""Non-rigid residual model on top of a homography: the viewpoint-variation answer.

A homography is exact for a flat scene seen by a pin-hole camera. Chandrayaan-2's
cameras are push-broom: every scan line has its own exposure time and attitude
(platform jitter), and terrain relief shifts a point by height x tan(view angle)
along the look direction (parallax) -- off-nadir TMC-2 fore/aft views and
rolled OHRC passes see hundreds of metres of it over crater walls. Neither is
projective, so a single homography leaves a smooth, systematic residual field.

This module measures that field and models it:

    q = p + d(p),    p = H(x)

where `x` is a source pixel, `H` the fitted homography and `d` a smooth 2D
displacement in reference pixels (a thin-plate spline through robustly binned
tile residuals). The smoothing strength is chosen by *spatially blocked*
cross-validation -- held-out cells are predicted from their neighbours -- and the
field is only adopted if it beats the plain homography on held-out data, so it
cannot fit noise. The reliable accuracy figure is the held-out RMSE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import map_coordinates

from algo.geometry.analysis import apply_homography

_SMOOTHINGS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)


@dataclass
class NonRigidModel:
    """Homography `H` (source -> reference) plus an optional smooth displacement field.

    `field_fn` maps reference-frame points p (N, 2) to displacements (N, 2); it is a thin-plate spline
    when freshly fitted and a bilinear lattice lookup when loaded back from JSON."""

    H: np.ndarray
    field_fn: Callable[[np.ndarray], np.ndarray] | None = None
    info: dict = field(default_factory=dict)

    # -- forward --------------------------------------------------------------------------------
    def displacement(self, p: np.ndarray) -> np.ndarray:
        p = np.asarray(p, dtype=np.float64).reshape(-1, 2)
        if self.field_fn is None:
            return np.zeros_like(p)
        return np.asarray(self.field_fn(p), dtype=np.float64)

    def to_reference(self, x: np.ndarray) -> np.ndarray:
        p = apply_homography(self.H, x)
        return p + self.displacement(p)

    def with_source_matrix(self, S: np.ndarray) -> "NonRigidModel":
        """The same mapping for a source image whose pixel coords relate to this model's by `S`
        (decimated crop -> full-resolution crop). The field lives in the reference frame, so it is unchanged."""
        return NonRigidModel(H=np.asarray(self.H) @ np.asarray(S, dtype=np.float64), field_fn=self.field_fn, info=self.info)

    def with_reference_offset(self, row: float, col: float) -> "NonRigidModel":
        """Re-express the model in a reference frame shifted by (row, col) pixels (local -> absolute raster)."""
        T = np.array([[1, 0, col], [0, 1, row], [0, 0, 1.0]])
        fn = self.field_fn
        shifted = None if fn is None else (lambda p, fn=fn: fn(np.asarray(p) - np.array([col, row])))
        return NonRigidModel(H=T @ np.asarray(self.H), field_fn=shifted, info=self.info)

    # -- inverse (reference -> source), used to warp the source image onto the reference grid ---
    def to_source(self, q: np.ndarray, iterations: int = 6) -> np.ndarray:
        q = np.asarray(q, dtype=np.float64).reshape(-1, 2)
        p = q.copy()
        if self.field_fn is not None:
            for _ in range(iterations):
                p = q - self.displacement(p)
        return apply_homography(np.linalg.inv(self.H), p)

    def source_map(self, out_shape: tuple[int, int], step: int = 16) -> tuple[np.ndarray, np.ndarray]:
        """Dense (map_x, map_y) giving, for each reference pixel, the source coordinate to sample.
        Evaluated on a coarse lattice and bilinearly interpolated (the field is smooth by construction)."""
        h, w = out_shape
        n_x, n_y = int(np.ceil((w - 1) / step)) + 2, int(np.ceil((h - 1) / step)) + 2
        gx, gy = np.meshgrid(np.arange(n_x) * float(step), np.arange(n_y) * float(step))
        src = self.to_source(np.stack([gx.ravel(), gy.ravel()], axis=1)).reshape(n_y, n_x, 2).astype(np.float32)
        lat_x = np.broadcast_to((np.arange(w, dtype=np.float32) / step)[None, :], (h, w))
        lat_y = np.broadcast_to((np.arange(h, dtype=np.float32) / step)[:, None], (h, w))
        mx = cv2.remap(np.ascontiguousarray(src[..., 0]), np.ascontiguousarray(lat_x), np.ascontiguousarray(lat_y), cv2.INTER_LINEAR)
        my = cv2.remap(np.ascontiguousarray(src[..., 1]), np.ascontiguousarray(lat_x), np.ascontiguousarray(lat_y), cv2.INTER_LINEAR)
        return mx, my

    def warp_source(self, source: np.ndarray, out_shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
        """Resample `source` into the reference frame. Returns (warped, valid_mask)."""
        mx, my = self.source_map(out_shape)
        warped = cv2.remap(source.astype(np.float32), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        ones = np.ones(source.shape[:2], np.uint8)
        valid = cv2.remap(ones, mx, my, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
        return warped, valid

    # -- serialisation ---------------------------------------------------------------------------
    def to_dict(self, bounds: tuple[float, float, float, float] | None = None, step: float = 32.0) -> dict:
        """JSON-friendly: the homography plus the field sampled on a lattice (reference px) over `bounds`
        = (x0, y0, x1, y1). The lattice is fine enough (32 px) that bilinear lookup reproduces the spline."""
        out: dict = {"homography": np.asarray(self.H).tolist(), "info": self.info}
        if self.field_fn is not None and bounds is not None:
            x0, y0, x1, y1 = bounds
            xs = np.arange(x0, x1 + step, step)
            ys = np.arange(y0, y1 + step, step)
            gx, gy = np.meshgrid(xs, ys)
            d = self.displacement(np.stack([gx.ravel(), gy.ravel()], axis=1)).reshape(gy.shape + (2,))
            out["field"] = {"x0": float(xs[0]), "y0": float(ys[0]), "step": float(step),
                            "dx": d[..., 0].round(3).tolist(), "dy": d[..., 1].round(3).tolist()}
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "NonRigidModel":
        H = np.array(d["homography"], dtype=np.float64)
        f = d.get("field")
        if not f:
            return cls(H=H, info=d.get("info", {}))
        dx, dy = np.array(f["dx"], dtype=np.float32), np.array(f["dy"], dtype=np.float32)
        x0, y0, step = float(f["x0"]), float(f["y0"]), float(f["step"])

        def fn(p: np.ndarray) -> np.ndarray:
            c = np.stack([(p[:, 1] - y0) / step, (p[:, 0] - x0) / step])
            return np.stack([map_coordinates(dx, c, order=1, mode="nearest"), map_coordinates(dy, c, order=1, mode="nearest")], axis=1)

        return cls(H=H, field_fn=fn, info=d.get("info", {}))


def _bin_residuals(p: np.ndarray, d: np.ndarray, w: np.ndarray, cell: float):
    """Median residual per `cell`-sized bin (robust to outliers, and thins thousands of overlapping tiles)."""
    key = np.floor(p / cell).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    nodes, vals, wts = [], [], []
    for k in range(len(uniq)):
        idx = np.flatnonzero(inv == k)
        nodes.append(np.median(p[idx], axis=0))
        vals.append(np.median(d[idx], axis=0))
        wts.append(w[idx].sum())
    return np.array(nodes), np.array(vals), np.array(wts)


def _fit_rbf(nodes, vals, scale, origin, smoothing):
    return RBFInterpolator((nodes - origin) / scale, vals, kernel="thin_plate_spline", smoothing=smoothing, degree=1)


def fit_nonrigid(
    source_xy: np.ndarray,
    reference_xy: np.ndarray,
    H: np.ndarray,
    weights: np.ndarray | None = None,
    cell: float = 48.0,
    min_gain: float = 0.08,
    min_abs_gain_px: float = 0.05,
    max_nodes: int = 2500,
) -> NonRigidModel:
    """Fit `d(p)` to the residuals of the homography `H` over tile matches and keep it only if a
    blocked cross-validation shows it predicts held-out residuals better than `H` alone.

    `cell` is the binning size in reference pixels (about the dense-stage tile stride).
    """
    H = np.asarray(H, dtype=np.float64)
    src = np.asarray(source_xy, dtype=np.float64)
    ref = np.asarray(reference_xy, dtype=np.float64)
    w = np.ones(len(src)) if weights is None else np.asarray(weights, dtype=np.float64)
    p = apply_homography(H, src)
    d = ref - p
    base = NonRigidModel(H=H)

    # robust pre-filter: drop gross outliers w.r.t. the homography itself
    r = np.hypot(d[:, 0], d[:, 1])
    mad = np.median(np.abs(r - np.median(r))) * 1.4826 + 1e-6
    keep = r < np.median(r) + 6.0 * mad + 1.0
    p, d, w = p[keep], d[keep], w[keep]
    if len(p) < 60:
        base.info = {"nonrigid": "skipped: too few matches"}
        return base

    extent = max(np.ptp(p[:, 0]), np.ptp(p[:, 1]), 1.0)
    cell = max(cell, extent / np.sqrt(max_nodes))
    nodes, vals, wts = _bin_residuals(p, d, w, cell)
    if len(nodes) < 40:
        base.info = {"nonrigid": "skipped: too few spatial cells"}
        return base

    origin = nodes.min(axis=0)
    scale = float(extent)

    # ---- blocked cross-validation over smoothing strengths ---------------------------------
    block = max(4.0 * cell, extent / 8.0)
    ib = np.floor((nodes - origin) / block).astype(int)
    fold = (ib[:, 0] % 2) + 2 * (ib[:, 1] % 2)

    def cv_error(smoothing: float | None) -> float:
        sq, wsum = 0.0, 0.0
        for f in range(4):
            test = fold == f
            train = ~test
            if test.sum() < 5 or train.sum() < 25:
                continue
            if smoothing is None:
                pred = np.zeros((test.sum(), 2))
            else:
                try:
                    rbf = _fit_rbf(nodes[train], vals[train], scale, origin, smoothing)
                    pred = rbf((nodes[test] - origin) / scale)
                except Exception:  # singular system for degenerate layouts
                    return float("inf")
            res = vals[test] - pred
            sq += float((wts[test] * (res**2).sum(axis=1)).sum())
            wsum += float(wts[test].sum())
        return float(np.sqrt(sq / wsum)) if wsum > 0 else float("nan")

    baseline = cv_error(None)
    if not np.isfinite(baseline):  # too few cells to hold any out: no held-out claim possible
        base.info = {"nonrigid": "skipped: too few cells for cross-validation", "nodes": int(len(nodes))}
        return base
    scores = {s: cv_error(s) for s in _SMOOTHINGS}
    best_s = min(scores, key=lambda s: scores[s] if np.isfinite(scores[s]) else float("inf"))
    best = scores[best_s]
    info = {
        "cv_rmse_homography_px": round(baseline, 4),
        "cv_rmse_nonrigid_px": round(best, 4),
        "smoothing": best_s,
        "nodes": int(len(nodes)),
    }
    if not np.isfinite(best) or best > (1.0 - min_gain) * baseline or (baseline - best) < min_abs_gain_px:
        info["nonrigid"] = "rejected: no held-out improvement over the homography"
        base.info = info
        return base

    rbf = _fit_rbf(nodes, vals, scale, origin, best_s)
    model = NonRigidModel(H=H, field_fn=lambda q, rbf=rbf: rbf((q - origin) / scale), info=info)
    disp = model.displacement(p[:: max(1, len(p) // 4000)])
    mag = np.hypot(disp[:, 0], disp[:, 1])
    info.update({
        "nonrigid": "adopted",
        "field_rms_px": round(float(np.sqrt((mag**2).mean())), 3),
        "field_max_px": round(float(mag.max()), 3),
        "cv_gain_pct": round(100.0 * (1.0 - best / baseline), 1),
    })
    return model
