"""Image representations for cross-illumination template matching.

Correlating raw (or merely contrast-normalised) intensity breaks when the Sun
moves: shading changes polarity, shadows relocate, and albedo contrast is
buried. Each representation here trades a different amount of the signal for
invariance, and `joint_ncc` correlates any of them (single- or multi-channel)
the same way, so they can be swapped or fused per scene:

  intensity  locally normalised image. Best when the lighting is similar, since it
             keeps every bit of texture; fails when the shading flips.
  orient     unsigned gradient-orientation tensor (doubled-angle form): invariant to
             contrast reversal, keeps only *where edges run and how strong they are*.
  cfog       channel features of oriented gradients (Ye et al. 2019): |directional
             derivative| in K orientations, smoothed -- polarity-invariant like
             `orient` but retains more than the dominant direction.
  edges      gradient magnitude only (the old experiment; kept for comparison).

`joint_ncc` is zero-mean normalised cross-correlation summed over channels
(for one channel it equals OpenCV's TM_CCOEFF_NORMED), so its value is directly
comparable across representations and can be averaged to fuse them.
"""

from __future__ import annotations

import cv2
import numpy as np

MODES = ("intensity", "orient", "cfog", "edges", "gmag", "dogabs", "logabs")  # any may carry "@sigma"
_EPS = 1e-6


def channels(mode: str, bins: int = 6) -> int:
    """Number of feature channels `features` returns for `mode`."""
    base = mode.split("@")[0]
    return {"orient": 2, "cfog": bins}.get(base, 1)


def local_normalize(img: np.ndarray, sigma: float | None = None) -> np.ndarray:
    x = img.astype(np.float32)
    sigma = sigma or max(6.0, 0.03 * max(x.shape))
    mean = cv2.GaussianBlur(x, (0, 0), sigma)
    diff = x - mean
    std = np.sqrt(cv2.GaussianBlur(diff * diff, (0, 0), sigma)) + 1e-3
    return diff / std


def _gradients(img: np.ndarray, smooth: float, norm_sigma: float | None) -> tuple[np.ndarray, np.ndarray]:
    x = local_normalize(img, norm_sigma)
    if smooth > 0:
        x = cv2.GaussianBlur(x, (0, 0), smooth)
    gx = cv2.Sobel(x, cv2.CV_32F, 1, 0, ksize=3, borderType=cv2.BORDER_REPLICATE)
    gy = cv2.Sobel(x, cv2.CV_32F, 0, 1, ksize=3, borderType=cv2.BORDER_REPLICATE)
    return gx, gy


def features(img: np.ndarray, mode: str, smooth: float = 1.0, bins: int = 6, norm_sigma: float | None = None) -> np.ndarray:
    return np.ascontiguousarray(_features(img, mode, smooth, bins, norm_sigma), dtype=np.float32)


def _features(img: np.ndarray, mode: str, smooth: float, bins: int, norm_sigma: float | None) -> np.ndarray:
    """(H, W, K) float32 feature stack for `mode`. Window and template must share `norm_sigma`
    (the local-normalisation scale), otherwise their contrast scaling differs. A mode may carry its own
    smoothing scale as "edges@2.5" (sigma in pixels)."""
    if "@" in mode:
        mode, s = mode.split("@")
        smooth = float(s)
    if mode == "intensity":
        return local_normalize(img, norm_sigma)[..., None]
    if mode == "dogabs":  # |band-pass|: responds to rims/blobs of either polarity
        x = local_normalize(img, norm_sigma)
        return np.abs(cv2.GaussianBlur(x, (0, 0), smooth) - cv2.GaussianBlur(x, (0, 0), 2.0 * smooth))[..., None]
    if mode == "logabs":  # |Laplacian of Gaussian|
        x = cv2.GaussianBlur(local_normalize(img, norm_sigma), (0, 0), smooth)
        return np.abs(cv2.Laplacian(x, cv2.CV_32F, ksize=3))[..., None]
    gx, gy = _gradients(img, smooth, norm_sigma)
    if mode == "gmag":  # gradient magnitude without the log compression
        return cv2.magnitude(gx, gy)[..., None]
    if mode == "edges":
        return np.log1p(cv2.magnitude(gx, gy))[..., None]
    if mode == "orient":
        # doubled-angle tensor: (gx + i gy)^2 is unchanged by g -> -g. Magnitude is compressed (sqrt of |g|^2
        # = |g|) so a few strong shadow edges do not drown the rest of the structure.
        mag2 = gx * gx + gy * gy
        scale = np.power(mag2 + 1e-6, -0.25, dtype=np.float32)  # |g|^2 * |g|^-1 -> keep |g|^1 overall
        u = (gx * gx - gy * gy) * scale
        v = (2 * gx * gy) * scale
        out = np.stack([u, v], axis=-1)
        # light smoothing: neighbouring orientations must overlap for correlation to be forgiving
        return cv2.GaussianBlur(out, (0, 0), 1.0)
    if mode == "cfog":
        chans = []
        for k in range(bins):
            th = np.pi * k / bins
            chans.append(np.abs(np.cos(th) * gx + np.sin(th) * gy))
        stack = cv2.GaussianBlur(np.stack(chans, axis=-1), (0, 0), 1.5)
        norm = np.sqrt((stack * stack).sum(axis=-1, keepdims=True)) + 1e-3
        return stack / norm
    raise ValueError(f"unknown structure mode {mode!r}")


def joint_ncc(win: np.ndarray, tmpl: np.ndarray) -> np.ndarray:
    """Zero-mean NCC of a (h, w, K) template against every position in a (H, W, K) window,
    summed jointly over channels: response (H-h+1, W-w+1), roughly in [-1, 1]."""
    H, W, K = win.shape
    h, w, _ = tmpl.shape
    if K == 1:  # OpenCV's own normalised version: one call instead of three
        return cv2.matchTemplate(np.ascontiguousarray(win[..., 0]), np.ascontiguousarray(tmpl[..., 0]), cv2.TM_CCOEFF_NORMED)
    n = float(h * w)
    cross = None
    win_energy = None
    tmpl_energy = 0.0
    for k in range(K):
        f = np.ascontiguousarray(win[..., k])
        t = np.ascontiguousarray(tmpl[..., k])
        c = cv2.matchTemplate(f, t, cv2.TM_CCOEFF)  # sum (f - mean_f_window)(t - mean_t) over the template
        # window energy in float64: sum(f^2) - sum(f)^2/n cancels catastrophically in float32 on flat windows
        sum_f = cv2.boxFilter(f, cv2.CV_64F, (w, h), anchor=(0, 0), normalize=False, borderType=cv2.BORDER_CONSTANT)
        sum_f2 = cv2.boxFilter(f * f, cv2.CV_64F, (w, h), anchor=(0, 0), normalize=False, borderType=cv2.BORDER_CONSTANT)
        e = (sum_f2 - sum_f * sum_f / n)[: H - h + 1, : W - w + 1]
        cross = c if cross is None else cross + c
        win_energy = e if win_energy is None else win_energy + e
        tmpl_energy += float(((t.astype(np.float64) - t.mean(dtype=np.float64)) ** 2).sum())
    denom = np.sqrt(np.maximum(win_energy, 0.0) * tmpl_energy) + 1e-3 * max(1.0, float(np.sqrt(tmpl_energy)))
    return np.clip(cross / denom, -1.0, 1.0).astype(np.float32)


def fused_response(win_imgs: dict[str, np.ndarray], tmpl_imgs: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    """Weighted mean of the `joint_ncc` surfaces of several representations."""
    total = 0.0
    out = None
    for mode, wt in weights.items():
        r = joint_ncc(win_imgs[mode], tmpl_imgs[mode])
        out = r * wt if out is None else out + r * wt
        total += wt
    return out / total
