"""Synthetic ground-truth registration scenes.

Real Chandrayaan-2 / LRO pairs have no ground truth, so accuracy claims about the
matcher can only be about internal consistency. These helpers build pairs whose
true source->reference mapping is known *exactly*, with each of the three problem-
statement difficulties dialled independently (or together):

  illumination  reference and source are the same terrain rendered by the DEM
                relighter at two different Sun azimuth/elevations (shading flips,
                shadows move), with a shared albedo texture;
  viewpoint     the source is sampled through a ground-truth homography (rotation,
                perspective) plus a smooth non-rigid field (terrain parallax) plus
                scan-line jitter;
  scale         the reference is block-averaged by `k` (a 5 m source against a
                100 m WAC-like reference is k = 20) or, reversed, the source is.

Ground truth is *forward*: for source pixel (x, y) the true reference pixel is
`q(x, y)`, and the source image is built by sampling the base scene at `q`, so no
inversion is involved anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates


# ----------------------------------------------------------------------------- scene content
def fractal_albedo(shape: tuple[int, int], rng: np.random.Generator, amplitude: float = 0.25) -> np.ndarray:
    """Multiplicative albedo texture (mean 1), shared by every rendering of the same terrain."""
    out = np.zeros(shape, np.float32)
    for sigma, w in ((2, 0.5), (6, 0.8), (18, 1.0), (50, 1.0), (140, 0.8)):
        # coarse octaves are generated at reduced size and upsampled: a sigma-140 blur at full size is very slow
        f = max(1, int(sigma // 6))
        small = rng.normal(size=(max(8, shape[0] // f), max(8, shape[1] // f))).astype(np.float32)
        small = cv2.GaussianBlur(small, (0, 0), sigma / f)
        n = cv2.resize(small, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC) if f > 1 else small
        out += w * n / (n.std() + 1e-9)
    out /= out.std() + 1e-9
    return (1.0 + amplitude * out).clip(0.4, 1.8).astype(np.float32)


def to_u8(img: np.ndarray, lo_pct: float = 0.5, hi_pct: float = 99.5) -> np.ndarray:
    lo, hi = np.percentile(img, [lo_pct, hi_pct])
    return np.clip((img - lo) / max(hi - lo, 1e-6) * 255.0, 0, 255).astype(np.float32)


# ----------------------------------------------------------------------------- geometry truth
@dataclass
class GeometryTruth:
    """source px -> base px: q = H(x) + d(H(x)) + jitter(y); all in *base* pixels."""

    H: np.ndarray
    field_lat: np.ndarray | None = None  # (n, n, 2) displacement lattice, base px
    field_step: float = 32.0
    jitter: np.ndarray | None = None  # (rows, 2) per source row, base px
    dem_parallax: tuple[np.ndarray, float] | None = None  # (height map in base px frame, metres->px factor*tan(view))
    dem_dir: tuple[float, float] = (0.0, 1.0)

    def to_base(self, xy: np.ndarray) -> np.ndarray:
        xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
        ones = np.ones((len(xy), 1))
        p = np.hstack([xy, ones]) @ self.H.T
        p = p[:, :2] / p[:, 2:3]
        q = p.copy()
        if self.field_lat is not None:
            c = np.stack([p[:, 1] / self.field_step, p[:, 0] / self.field_step])
            for k in range(2):
                q[:, k] += map_coordinates(self.field_lat[..., k], c, order=1, mode="nearest")
        if self.dem_parallax is not None:
            hmap, f = self.dem_parallax
            hv = map_coordinates(hmap, np.stack([p[:, 1], p[:, 0]]), order=1, mode="nearest")
            q[:, 0] += hv * f * self.dem_dir[0]
            q[:, 1] += hv * f * self.dem_dir[1]
        if self.jitter is not None:
            rows = np.clip(xy[:, 1], 0, len(self.jitter) - 1)
            for k in range(2):
                q[:, k] += np.interp(rows, np.arange(len(self.jitter)), self.jitter[:, k])
        return q


def smooth_lattice(shape_px: tuple[int, int], step: float, amp_px: float, wavelength_px: float, rng) -> np.ndarray:
    n_y, n_x = int(shape_px[0] / step) + 3, int(shape_px[1] / step) + 3
    out = np.zeros((n_y, n_x, 2), np.float32)
    for k in range(2):
        n = gaussian_filter(rng.normal(size=(n_y, n_x)).astype(np.float32), max(wavelength_px / step / 2.5, 0.5), mode="reflect")
        out[..., k] = n / (n.std() + 1e-9) * amp_px
    return out


def make_geometry(
    src_shape: tuple[int, int],
    base_shape: tuple[int, int],
    *,
    scale: float = 1.0,  # base px per source px
    rotation_deg: float = 0.0,
    perspective: float = 0.0,  # fractional foreshortening across the source frame
    field_amp_px: float = 0.0,  # non-rigid displacement RMS, base px
    field_wavelength_px: float = 900.0,
    jitter_amp_px: float = 0.0,
    jitter_wavelength_rows: float = 250.0,
    rng: np.random.Generator,
) -> GeometryTruth:
    sh, sw = src_shape
    bh, bw = base_shape
    ang = np.radians(rotation_deg)
    R = np.array([[np.cos(ang), -np.sin(ang), 0], [np.sin(ang), np.cos(ang), 0], [0, 0, 1.0]])
    S = np.diag([scale, scale, 1.0])
    P = np.array([[1, 0, 0], [0, 1, 0], [perspective / sw, perspective / sh * 0.5, 1.0]])
    Tc = np.array([[1, 0, -(sw - 1) / 2], [0, 1, -(sh - 1) / 2], [0, 0, 1.0]])
    Tb = np.array([[1, 0, (bw - 1) / 2], [0, 1, (bh - 1) / 2], [0, 0, 1.0]])
    H = Tb @ R @ S @ P @ Tc
    truth = GeometryTruth(H=H)
    if field_amp_px > 0:
        truth.field_lat = smooth_lattice(base_shape, truth.field_step, field_amp_px, field_wavelength_px, rng)
    if jitter_amp_px > 0:
        j = np.zeros((sh, 2), np.float32)
        for k in range(2):
            n = gaussian_filter(rng.normal(size=sh).astype(np.float32), jitter_wavelength_rows / 2.5)
            j[:, k] = n / (n.std() + 1e-9) * jitter_amp_px
        truth.jitter = j
    return truth


def render_source(base: np.ndarray, truth: GeometryTruth, src_shape: tuple[int, int], scale: float,
                  rng: np.random.Generator, noise: float = 0.02, gain: float = 1.0, gamma: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Sample `base` through the truth map (anti-aliased for scale > 1). Returns (source, q) with
    q the (h, w, 2) ground-truth base coordinates of every source pixel."""
    sh, sw = src_shape
    yy, xx = np.mgrid[0:sh, 0:sw]
    q = truth.to_base(np.stack([xx.ravel(), yy.ravel()], axis=1)).reshape(sh, sw, 2)
    img = base.astype(np.float32)
    if scale > 1.05:
        img = cv2.GaussianBlur(img, (0, 0), 0.45 * scale)
    src = cv2.remap(img, q[..., 0].astype(np.float32), q[..., 1].astype(np.float32), cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    src = np.clip(src, 0, None) ** gamma * gain
    if noise > 0:
        src = src + rng.normal(0, noise * max(float(np.percentile(src, 95)), 1.0), src.shape).astype(np.float32)
    return src.astype(np.float32), q


def downsample(img: np.ndarray, k: float) -> np.ndarray:
    if k <= 1.0001:
        return img.astype(np.float32)
    h, w = img.shape
    return cv2.resize(img.astype(np.float32), (max(8, int(round(w / k))), max(8, int(round(h / k)))), interpolation=cv2.INTER_AREA)


def base_to_ref_matrix(k: float, ref_shape: tuple[int, int], base_shape: tuple[int, int]) -> np.ndarray:
    """base px -> reference px for a reference made by block-averaging the base by `k`."""
    fx, fy = base_shape[1] / ref_shape[1], base_shape[0] / ref_shape[0]
    return np.array([[1 / fx, 0, 0.5 / fx - 0.5], [0, 1 / fy, 0.5 / fy - 0.5], [0, 0, 1.0]])


# ----------------------------------------------------------------------------- prior error
def perturb_prior(H_true_ref: np.ndarray, src_shape: tuple[int, int], shift_px: float, rot_deg: float,
                  scale_err: float, rng: np.random.Generator) -> np.ndarray:
    """A deliberately wrong prior: the true (homography part of the) mapping with an error of
    `shift_px` reference pixels, `rot_deg` of rotation about the frame centre and `scale_err` fractional scale."""
    sh, sw = src_shape
    c = apply_h(H_true_ref, np.array([[(sw - 1) / 2, (sh - 1) / 2]]))[0]
    a = rng.uniform(0, 2 * np.pi)
    t = np.array([[1, 0, shift_px * np.cos(a)], [0, 1, shift_px * np.sin(a)], [0, 0, 1.0]])
    th = np.radians(rot_deg * rng.choice([-1, 1]))
    s = 1.0 + scale_err * rng.choice([-1, 1])
    Rs = np.array([[s * np.cos(th), -s * np.sin(th), 0], [s * np.sin(th), s * np.cos(th), 0], [0, 0, 1.0]])
    Tc = np.array([[1, 0, c[0]], [0, 1, c[1]], [0, 0, 1.0]])
    Tn = np.array([[1, 0, -c[0]], [0, 1, -c[1]], [0, 0, 1.0]])
    return t @ Tc @ Rs @ Tn @ H_true_ref


def apply_h(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    h = np.hstack([pts, np.ones((len(pts), 1))]) @ np.asarray(H).T
    return h[:, :2] / h[:, 2:3]


# ----------------------------------------------------------------------------- scenario
@dataclass
class Pair:
    source: np.ndarray
    reference: np.ndarray
    reference_gsd: float
    H_prior: np.ndarray  # source px -> reference px (the deliberately wrong starting guess)
    truth_ref: callable  # (N,2) source px -> (N,2) true reference px
    meta: dict = field(default_factory=dict)


def evaluate_model(model_to_reference, pair: Pair, src_shape: tuple[int, int], margin: float = 0.08, n: int = 24) -> dict:
    """Error of an estimated source->reference mapping against the truth over a lattice of source points."""
    sh, sw = src_shape
    xs = np.linspace(margin * sw, (1 - margin) * sw, n)
    ys = np.linspace(margin * sh, (1 - margin) * sh, n)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
    err = np.hypot(*(model_to_reference(pts) - pair.truth_ref(pts)).T)
    return {
        "rmse_px": float(np.sqrt(np.mean(err**2))),
        "p95_px": float(np.percentile(err, 95)),
        "max_px": float(err.max()),
        "rmse_m": float(np.sqrt(np.mean(err**2)) * pair.reference_gsd),
    }
