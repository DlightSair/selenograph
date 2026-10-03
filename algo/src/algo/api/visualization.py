"""Renders a run's result as a set of *separate* images plus a manifest, on
demand, so the UI can give each one its own zoom window.

Small panels cannot convey the quality of a fit over a 17000-line strip, and a
degenerate transform can look plausible in a single summary view. The images
therefore show what the transform actually *does* (footprint + warped grid
overlaid on the reference), aligned close-ups at native resolution, a
false-colour overlay that makes misalignment visible as colour fringes, plus
numeric context (conditioning, scale vs GSD, independent anchors, agreement
with the control-grid prior) that doesn't depend on judging a picture.
"""

from __future__ import annotations

import csv
import json
import threading
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")  # headless -- runs inside the API server process, no display
import matplotlib.pyplot as plt
import numpy as np

from algo.api._crops import load_aoi_context
from algo.geometry.analysis import (
    apply_homography,
    decompose_transform,
    distinct_anchors,
    health_checks,
    local_scale,
    prior_offsets,
)
from algo.geometry.nonrigid import NonRigidModel
from algo.preprocessing.grid import control_grid_prior_homography

VIZ_VERSION = 5  # bump to invalidate every cached viz/ directory after changing what is rendered
_MAX_SIDE = 3000  # longest edge of a rendered image, px -- big enough to zoom into, small enough to load fast
_SOURCE_GAMMA = 0.55
_lock = threading.Lock()

_PALETTE_BGR = [(60, 60, 230), (230, 140, 40), (60, 170, 60), (200, 60, 170), (30, 190, 220), (150, 100, 40)]


# ---------------------------------------------------------------- image helpers

def _stretch(
    a: np.ndarray, valid: np.ndarray | None = None, lo: float = 2, hi: float = 98, gamma: float = 1.0
) -> np.ndarray:
    """Percentile contrast stretch to uint8 (then gamma), ignoring no-data (zeros / invalid).
    Raw source DN is dark with sparse bright speckle (near-noon TMC-2 especially), so it gets a
    wider percentile range and gamma < 1 to look like a normal photograph."""
    a = a.astype(np.float32)
    use = (a > 0) if valid is None else (valid & (a > 0))
    sample = a[use] if use.any() else a.ravel()
    sample = sample[:: max(1, sample.size // 200_000)]
    lo_v, hi_v = np.percentile(sample, [lo, hi])
    scaled = np.clip((a - lo_v) / max(hi_v - lo_v, 1e-6), 0, 1)
    return (scaled ** gamma * 255).astype(np.uint8)


def _local_normalize(gray01: np.ndarray, sigma: float) -> np.ndarray:
    """Subtract the local mean and divide by the local spread: removes the
    sun-angle brightness difference between sensors and leaves structure
    (rims, ridges, crater edges), which is what should line up."""
    img = gray01.astype(np.float32)
    mean = cv2.GaussianBlur(img, (0, 0), sigma)
    diff = img - mean
    std = np.sqrt(cv2.GaussianBlur(diff * diff, (0, 0), sigma)) + 1e-3
    return np.clip(diff / std * 0.22 + 0.5, 0, 1)


def _downscale(a: np.ndarray, max_side: int = _MAX_SIDE, min_side: int = 1400) -> tuple[np.ndarray, float]:
    """Resize so the long edge lies in [min_side, max_side]: big strips shrink, and a small
    (e.g. 100 m/px WAC) crop is enlarged so zooming into it isn't a handful of fat pixels."""
    long_side = max(a.shape[:2])
    scale = max_side / long_side if long_side > max_side else (min_side / long_side if long_side < min_side else 1.0)
    if scale == 1.0:
        return a.astype(np.float32), 1.0
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.resize(a.astype(np.float32), None, fx=scale, fy=scale, interpolation=interp), scale


def _false_colour(ref01: np.ndarray, warped01: np.ndarray) -> np.ndarray:
    """BGR uint8: reference -> magenta, warped source -> green. Aligned
    structure sums to grey/white; misalignment leaves colour fringes."""
    out = np.stack([ref01, warped01, ref01], axis=-1)  # B, G, R
    return (out * 255).astype(np.uint8)


def _bbox(mask: np.ndarray, pad_frac: float = 0.03) -> tuple[int, int, int, int]:
    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    if rows.size == 0:
        return 0, mask.shape[0], 0, mask.shape[1]
    pad_r, pad_c = int(mask.shape[0] * pad_frac), int(mask.shape[1] * pad_frac)
    return (
        max(rows[0] - pad_r, 0), min(rows[-1] + 1 + pad_r, mask.shape[0]),
        max(cols[0] - pad_c, 0), min(cols[-1] + 1 + pad_c, mask.shape[1]),
    )


def _spread_pick(points: np.ndarray, k: int) -> list[int]:
    """Up to k indices spread across `points` (farthest-point sampling, starting at index 0)."""
    if len(points) <= k:
        return list(range(len(points)))
    chosen = [0]
    dist = np.hypot(*(points - points[0]).T)
    while len(chosen) < k:
        nxt = int(np.argmax(dist))
        chosen.append(nxt)
        dist = np.minimum(dist, np.hypot(*(points - points[nxt]).T))
    return chosen


def _save_png(path: Path, image: np.ndarray) -> None:
    cv2.imwrite(str(path), image, [cv2.IMWRITE_PNG_COMPRESSION, 5])


def _save_fig(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _numbered_markers(image_gray8: np.ndarray, points_xy: np.ndarray) -> np.ndarray:
    img = cv2.cvtColor(image_gray8, cv2.COLOR_GRAY2BGR)
    radius = max(9, int(0.012 * max(img.shape[:2])))
    thickness = max(2, radius // 5)
    for n, (x, y) in enumerate(points_xy, start=1):
        if not (0 <= x < img.shape[1] and 0 <= y < img.shape[0]):
            continue
        colour = _PALETTE_BGR[(n - 1) % len(_PALETTE_BGR)]
        centre = (int(round(x)), int(round(y)))
        cv2.circle(img, centre, radius, (255, 255, 255), thickness + 2)
        cv2.circle(img, centre, radius, colour, thickness)
        cv2.putText(
            img, str(n), (centre[0] + radius + 4, centre[1] + radius // 2),
            cv2.FONT_HERSHEY_SIMPLEX, radius / 14, (0, 0, 0), thickness + 3, cv2.LINE_AA,
        )
        cv2.putText(
            img, str(n), (centre[0] + radius + 4, centre[1] + radius // 2),
            cv2.FONT_HERSHEY_SIMPLEX, radius / 14, (255, 255, 255), thickness, cv2.LINE_AA,
        )
    return img


# ------------------------------------------------------------------- rendering

def _grid_polylines(mapping, width: float, height: float, n: int = 9):
    """`mapping` is a (3x3 homography) or a callable taking (N,2) source points to reference points."""
    fn = (lambda pts: apply_homography(mapping, pts)) if isinstance(mapping, np.ndarray) else mapping
    ts = np.linspace(0, 1, 80)
    lines = []
    for f in np.linspace(0, 1, n):
        lines.append(fn(np.stack([np.full_like(ts, f * width), ts * height], axis=1)))
        lines.append(fn(np.stack([ts * width, np.full_like(ts, f * height)], axis=1)))
    border = fn(np.array([[0, 0], [width, 0], [width, height], [0, height], [0, 0]], dtype=float))
    return lines, border


def _render_footprint(path, ref_gray8, scale, H_local, H_prior_local, src_wh, anchors_ref_local, ref_hw):
    h, w = ref_hw
    fig_h = float(np.clip(9 * (h / w), 6, 14))
    fig, ax = plt.subplots(figsize=(9, fig_h + 1))
    ax.imshow(ref_gray8, cmap="gray", extent=(0, w, h, 0))

    grid_lines, border = _grid_polylines(H_local, *src_wh)
    for line in grid_lines:
        ax.plot(line[:, 0], line[:, 1], color="#ff9f1c", lw=0.8, alpha=0.75)
    ax.plot(border[:, 0], border[:, 1], color="#ff2a2a", lw=2.4, label="Source footprint (fitted transform)")
    if H_prior_local is not None:
        _, prior_border = _grid_polylines(H_prior_local, *src_wh, n=2)
        ax.plot(prior_border[:, 0], prior_border[:, 1], color="#3fa9ff", lw=2.2, ls="--",
                label="Source footprint (control-grid prior)")
    if len(anchors_ref_local):
        ax.scatter(anchors_ref_local[:, 0], anchors_ref_local[:, 1], s=60, c="yellow",
                   edgecolors="black", zorder=5, label="Matched locations")
    ax.set_xlim(-0.2 * w, 1.2 * w)
    ax.set_ylim(1.1 * h, -0.1 * h)
    ax.set_title("What the transform does to the source strip")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.92)
    ax.set_xlabel("reference crop x (px)")
    ax.set_ylabel("reference crop y (px)")
    _save_fig(fig, path)


def _render_patches(path, ref_full, warped_full, valid_full, centres_local):
    half = 64
    rows = []
    for n, (cx, cy) in centres_local:
        x0, y0 = int(round(cx)) - half, int(round(cy)) - half
        if x0 < 0 or y0 < 0 or y0 + 2 * half > ref_full.shape[0] or x0 + 2 * half > ref_full.shape[1]:
            continue
        ref_p = ref_full[y0:y0 + 2 * half, x0:x0 + 2 * half]
        warped_p = warped_full[y0:y0 + 2 * half, x0:x0 + 2 * half]
        valid_p = valid_full[y0:y0 + 2 * half, x0:x0 + 2 * half]
        if valid_p.mean() < 0.5:
            continue
        ref01 = _local_normalize(_stretch(ref_p).astype(np.float32) / 255, 6)
        warped01 = _local_normalize(_stretch(warped_p, valid_p).astype(np.float32) / 255, 6)
        rows.append((n, ref01, warped01))
    if not rows:
        return False

    fig, axes = plt.subplots(len(rows), 3, figsize=(9.5, 3.2 * len(rows)), squeeze=False)
    for (n, ref01, warped01), ax_row in zip(rows, axes):
        ax_row[0].imshow(ref01, cmap="gray", interpolation="bicubic")
        ax_row[1].imshow(warped01, cmap="gray", interpolation="bicubic")
        ax_row[2].imshow(_false_colour(ref01, warped01)[..., ::-1], interpolation="bicubic")
        ax_row[0].set_ylabel(f"#{n}", rotation=0, labelpad=18, fontsize=13, fontweight="bold")
        for ax in ax_row:
            ax.set_xticks([])
            ax.set_yticks([])
    for ax, title in zip(axes[0], ("Reference", "Warped source", "Overlay (magenta = ref, green = source)")):
        ax.set_title(title, fontsize=10)
    _save_fig(fig, path)
    return True


def _render_residuals(path, anchors_ref_local, anchor_resid, all_mag, rmse, ref_hw):
    h, w = ref_hw
    fig, (ax_q, ax_h) = plt.subplots(1, 2, figsize=(12, 7), gridspec_kw={"width_ratios": [1, 1.2]})
    mags = np.hypot(anchor_resid[:, 0], anchor_resid[:, 1])
    gain = 0.06 * max(h, w) / max(float(mags.max()), 0.25) if len(mags) else 1.0
    ax_q.quiver(
        anchors_ref_local[:, 0], anchors_ref_local[:, 1], anchor_resid[:, 0] * gain, anchor_resid[:, 1] * gain,
        mags, angles="xy", scale_units="xy", scale=1, cmap="plasma", width=0.006,
    )
    ax_q.scatter(anchors_ref_local[:, 0], anchors_ref_local[:, 1], s=14, c="black", zorder=3)
    ax_q.set_xlim(0, w)
    ax_q.set_ylim(h, 0)
    ax_q.set_aspect("equal")
    ax_q.set_title(f"Remaining error per anchor (arrows magnified x{gain:.0f})")
    ax_q.set_xlabel("reference crop x (px)")
    ax_q.set_ylabel("reference crop y (px)")

    ax_h.hist(all_mag, bins=min(25, max(len(all_mag) // 2, 5)), color="#3b6ea5", edgecolor="black")
    if rmse is not None:
        ax_h.axvline(rmse, color="red", lw=2, label=f"RMSE {rmse:.2f} px")
        ax_h.legend()
    ax_h.set_title("Distribution of per-match reprojection error")
    ax_h.set_xlabel("error (reference px)")
    ax_h.set_ylabel("matches")
    _save_fig(fig, path)


def _render_prior(path, predicted_local, matched_local, offsets, ref_hw):
    h, w = ref_hw
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12, 7), gridspec_kw={"width_ratios": [1, 1.2]})
    for i, (p, m) in enumerate(zip(predicted_local, matched_local), start=1):
        ax_a.annotate("", xy=m, xytext=p, arrowprops=dict(arrowstyle="->", color="#444", lw=1.2))
        ax_a.text(m[0], m[1], f" {i}", fontsize=8, color="red")
    ax_a.scatter(*predicted_local.T, s=40, facecolors="none", edgecolors="#3fa9ff", lw=1.8, label="Prior (control grid)")
    ax_a.scatter(*matched_local.T, s=26, c="red", label="Where the match landed")
    ax_a.set_xlim(-0.1 * w, 1.1 * w)
    ax_a.set_ylim(1.05 * h, -0.05 * h)
    ax_a.set_aspect("equal")
    ax_a.legend(loc="lower center", fontsize=8)
    ax_a.set_title("Match vs. independent prior (arrow: prior -> match)")
    ax_a.set_xlabel("reference crop x (px)")
    ax_a.set_ylabel("reference crop y (px)")

    dist = np.hypot(offsets[:, 0], offsets[:, 1])
    ax_b.bar(range(1, len(dist) + 1), dist, color="#c0392b")
    ax_b.axhline(float(np.median(dist)), color="black", ls="--", label=f"median {np.median(dist):.0f} px")
    ax_b.set_title("Distance from prior, per anchor (short and similar = a real fit)")
    ax_b.set_xlabel("anchor #")
    ax_b.set_ylabel("distance (reference px)")
    ax_b.legend()
    _save_fig(fig, path)


def _render_nonrigid(path, model_local, H_local, src_xy, ref_local, ref_hw, ref_gsd):
    """What the non-rigid field adds: where and how far it moves things, and the error before/after."""
    h, w = ref_hw
    fig, (ax_f, ax_h) = plt.subplots(1, 2, figsize=(13, 7.5), gridspec_kw={"width_ratios": [1, 1.15]})
    step = max(32.0, max(h, w) / 90)
    xs, ys = np.arange(0, w + step, step), np.arange(0, h + step, step)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
    d = model_local.displacement(pts).reshape(gy.shape + (2,)) * ref_gsd  # metres
    mag = np.hypot(d[..., 0], d[..., 1])
    im = ax_f.imshow(mag, extent=(0, xs[-1], ys[-1], 0), cmap="magma", vmin=0)
    q = max(1, int(round(len(xs) / 16)))
    ax_f.quiver(gx[::q, ::q], gy[::q, ::q], d[::q, ::q, 0], d[::q, ::q, 1], color="white", angles="xy",
                scale_units="xy", scale=max(float(mag.max()), 1e-6) / (step * q * 1.3), width=0.004)
    fp = apply_homography(H_local, src_xy)
    ax_f.scatter(fp[:, 0], fp[:, 1], s=1, c="cyan", alpha=0.25)
    ax_f.set_xlim(0, w)
    ax_f.set_ylim(h, 0)
    ax_f.set_aspect("equal")
    ax_f.set_title(f"Non-rigid correction on top of the homography (peak {mag.max():.1f} m, rms {np.sqrt((mag**2).mean()):.1f} m)")
    ax_f.set_xlabel("reference crop x (px)")
    ax_f.set_ylabel("reference crop y (px)")
    fig.colorbar(im, ax=ax_f, fraction=0.04, label="displacement (m)")

    before = np.hypot(*(fp - ref_local).T) * ref_gsd
    after = np.hypot(*(model_local.to_reference(src_xy) - ref_local).T) * ref_gsd
    top = max(float(np.percentile(before, 99)), 1e-6)
    bins = np.linspace(0, top, 40)
    ax_h.hist(before, bins=bins, alpha=0.55, color="#c0392b", label=f"homography only (rms {np.sqrt((before**2).mean()):.1f} m)")
    ax_h.hist(after, bins=bins, alpha=0.65, color="#2e86c1", label=f"with field (rms {np.sqrt((after**2).mean()):.1f} m)")
    ax_h.set_title("Per-match error, before and after the field")
    ax_h.set_xlabel("error (m)")
    ax_h.set_ylabel("matches")
    ax_h.legend()
    _save_fig(fig, path)


def _render(config: dict, out_dir: Path, viz_dir: Path) -> dict:
    transform_path = out_dir / "transform.json"
    matches_path = out_dir / "matches.csv"
    if not transform_path.exists() or not matches_path.exists():
        raise FileNotFoundError("run has no fitted transform/matches to visualize (failed, or too few matches)")
    viz_dir.mkdir(parents=True, exist_ok=True)

    tj = json.loads(transform_path.read_text())
    H = np.array(tj["homography"], dtype=np.float64)  # full-resolution source crop px -> reference raster px
    metrics_path = out_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    rmse = metrics.get("rmse")
    with open(matches_path, newline="") as f:
        rows = list(csv.DictReader(f))
    src_xy = np.array([[float(r["source_x"]), float(r["source_y"])] for r in rows])
    ref_xy = np.array([[float(r["reference_x"]), float(r["reference_y"])] for r in rows])
    conf = np.array([float(r["confidence"]) for r in rows])

    ctx = load_aoi_context(config, decimation="auto", with_relit=True)
    off = np.array([ctx.reference_col_offset, ctx.reference_row_offset], dtype=np.float64)
    to_local = np.array([[1, 0, -off[0]], [0, 1, -off[1]], [0, 0, 1]], dtype=np.float64)
    H_local = to_local @ H
    nr = tj.get("nonrigid") or {}
    model = NonRigidModel.from_dict({"homography": H_local.tolist(), "field": nr.get("field"), "info": nr.get("info", {})})
    model_dec = model.with_source_matrix(ctx.source_to_full)  # for the (possibly decimated) source image
    H_prior = control_grid_prior_homography(ctx.grid, ctx.source_window, ctx.reference_transform, ctx.reference_crs)
    H_prior_local = to_local @ H_prior if H_prior is not None else None

    source_meta, reference_meta = ctx.source_meta, ctx.reference_meta
    expected_scale = (
        source_meta.gsd / reference_meta.gsd if source_meta and reference_meta and source_meta.gsd and reference_meta.gsd else None
    )
    ref_gsd = reference_meta.gsd if reference_meta and reference_meta.gsd else 1.0

    # Independent anchors: highest-confidence first, near-duplicates (densified points) merged.
    S_inv = np.linalg.inv(ctx.source_to_full)
    order = np.argsort(-conf)
    anchor_idx = order[distinct_anchors(src_xy[order])]
    n_anchors = len(anchor_idx)
    anchor_idx = anchor_idx[_spread_pick(ref_xy[anchor_idx], 40)]  # keep the numbered views readable
    anchors_src = src_xy[anchor_idx]  # full-resolution crop px
    anchors_ref_local = ref_xy[anchor_idx] - off

    ref_h, ref_w = ctx.reference_crop.shape
    src_h_dec, src_w_dec = ctx.source_crop.shape
    src_w, src_h = src_w_dec * ctx.source_to_full[0, 0], src_h_dec * ctx.source_to_full[1, 1]  # full-res size
    warped, valid = model_dec.warp_source(ctx.source_crop, (ref_h, ref_w))

    items: list[dict] = []

    def add(name: str, title: str, caption: str, group: str) -> None:
        items.append({"name": name, "title": title, "caption": caption, "group": group})

    # --- footprint (whole reference crop, with the source strip's footprint and warped grid)
    ref_small, _ = _downscale(ctx.reference_crop, 1800)
    _render_footprint(
        viz_dir / "footprint.png", _stretch(ref_small, ref_small > 0), 1.0, model.to_reference, H_prior_local,
        (src_w, src_h), anchors_ref_local, (ref_h, ref_w),
    )
    add("footprint", "Where the transform puts the source",
        "Red outline: the whole source strip after the fitted transform. Orange grid: the source's own pixel "
        "grid warped by it, which is what the transform actually does (scale, rotation, bending). Blue dashed: "
        "where the control-grid prior says the strip belongs. Yellow: matched locations. A sane fit is a "
        "slightly-rotated rectangle sitting on the blue one.", "What the transform does")

    # --- aligned comparison images, cropped to the area the warped source actually covers
    r0, r1, c0, c1 = _bbox(valid)
    ref_r, warped_r, valid_r = ctx.reference_crop[r0:r1, c0:c1], warped[r0:r1, c0:c1], valid[r0:r1, c0:c1]
    ref_d, scale = _downscale(ref_r)
    warped_d, _ = _downscale(warped_r * valid_r)
    valid_f, _ = _downscale(valid_r.astype(np.float32))
    valid_d = valid_f > 0.5
    warped_d = np.where(valid_d, warped_d / np.maximum(valid_f, 1e-3), 0)

    ref8, warped8 = _stretch(ref_d, ref_d > 0), _stretch(warped_d, valid_d, 1, 99.7, _SOURCE_GAMMA)
    sigma = max(4.0, 0.004 * max(ref_d.shape))
    ref_ln = _local_normalize(ref8.astype(np.float32) / 255, sigma)
    warped_ln = np.where(valid_d, _local_normalize(warped8.astype(np.float32) / 255, sigma), 0)

    _save_png(viz_dir / "blend.png", np.where(valid_d[..., None], _false_colour(ref_ln, warped_ln), 0).astype(np.uint8))
    add("blend", "Overlay: reference vs. warped source",
        "Reference in magenta, warped source in green, both local-contrast-normalized so the sun-angle "
        "brightness difference drops out. Where they line up the structure is grey/white; misalignment "
        "shows as magenta/green fringes. A wrong fit shows two unrelated textures.", "What the transform does")

    tile = max(32, int(min(ref_d.shape) / 10))
    yy, xx = np.indices(ref_d.shape)
    use_warped = (((yy // tile) + (xx // tile)) % 2 == 0) & valid_d
    _save_png(viz_dir / "checker.png", (np.where(use_warped, warped_ln, ref_ln) * 255).astype(np.uint8))
    add("checker", "Checkerboard",
        "Alternating tiles of the reference and the warped source. Craters, ridges and edges should continue "
        "straight across tile boundaries; offsets or unrelated texture at the seams mean misalignment.",
        "What the transform does")

    centres = [(i + 1, p) for i, p in enumerate(anchors_ref_local)]
    picked = _spread_pick(anchors_ref_local, 6) if len(anchors_ref_local) else []
    if _render_patches(viz_dir / "patches.png", ctx.reference_crop, warped, valid, [centres[i] for i in picked]):
        add("patches", "Close-ups at matched locations",
            "Windows around spread-out anchors in the reference frame: reference, warped source, and their overlay. "
            "This is the pixel-level view; the same crater should sit in the same spot in all three.",
            "What the transform does")

    warped_png = cv2.cvtColor(warped8, cv2.COLOR_GRAY2BGRA)
    warped_png[..., 3] = np.where(valid_d, 255, 0).astype(np.uint8)
    _save_png(viz_dir / "warped.png", warped_png)
    add("warped", "Warped source",
        "The source resampled into the reference's pixel grid with the fitted transform (transparent where it "
        "has no coverage). Compare with the reference: a correct fit looks like the same terrain.",
        "What the transform does")
    _save_png(viz_dir / "reference.png", ref8)
    add("reference", "Reference (same region)",
        "The reference cropped to the area the warped source covers, for side-by-side comparison.",
        "What the transform does")

    # --- illumination: the Sun-matched DEM layer, when the run used one
    if ctx.relit is not None:
        relit_r = ctx.relit[r0:r1, c0:c1]
        relit_d, _ = _downscale(relit_r)
        relit8 = _stretch(relit_d, relit_d > 0)
        _save_png(viz_dir / "relit.png", relit8)
        sun = (f"azimuth {source_meta.sun_azimuth:.0f}°, elevation {source_meta.sun_elevation:.1f}°"
               if source_meta and source_meta.sun_azimuth is not None else "the source's Sun")
        add("relit", "DEM re-lit with the source's Sun",
            f"The terrain model rendered with {sun} (shading and cast shadows). The shading depends on illumination, "
            "the DEM does not, so this layer looks like the source whatever the reference's lighting was; it is "
            "correlated against the source alongside the reference image.", "Illumination")
        relit_ln = _local_normalize(relit8.astype(np.float32) / 255, sigma)
        _save_png(viz_dir / "blend_relit.png", np.where(valid_d[..., None], _false_colour(relit_ln, warped_ln), 0).astype(np.uint8))
        add("blend_relit", "Overlay: re-lit DEM vs. warped source",
            "Re-lit DEM in magenta, warped source in green: with the lighting matched, shadows and slopes should "
            "coincide.", "Illumination")

    # --- numbered matches on each image
    src_small, s_scale = _downscale(ctx.source_crop)
    src8 = _stretch(src_small, src_small > 0, 1, 99.7, _SOURCE_GAMMA)
    anchors_src_dec = apply_homography(S_inv, anchors_src)
    _save_png(viz_dir / "matches_source.png", _numbered_markers(src8, anchors_src_dec * s_scale))
    add("matches_source", "Matches on the source",
        "Independent anchors (near-duplicate points merged), numbered. The same number marks the same "
        "landform on the reference; check that a few of them really do.", "Matches")
    ref_full_small, r_scale = _downscale(ctx.reference_crop)
    ref_full8 = _stretch(ref_full_small, ref_full_small > 0)
    _save_png(viz_dir / "matches_reference.png", _numbered_markers(ref_full8, anchors_ref_local * r_scale))
    add("matches_reference", "Matches on the reference",
        "Where each numbered anchor landed on the reference crop. If they jump around with no relation to "
        "their order on the source, the matcher locked onto look-alike terrain.", "Matches")

    # --- diagnostics
    ref_local_all = ref_xy - off
    predicted = model.to_reference(src_xy)
    resid_all = ref_local_all - predicted
    resid_anchor = resid_all[anchor_idx]
    _render_residuals(
        viz_dir / "residuals.png", anchors_ref_local, resid_anchor, np.hypot(resid_all[:, 0], resid_all[:, 1]),
        rmse, (ref_h, ref_w),
    )
    add("residuals", "Residual error",
        "Left: the leftover error at each anchor after the fit, as magnified arrows. Right: histogram of "
        "per-match error. Small is necessary but not sufficient: a collapsed transform also scores low.",
        "Diagnostics")

    if model.field_fn is not None:
        _render_nonrigid(viz_dir / "nonrigid.png", model, H_local, src_xy, ref_local_all, (ref_h, ref_w), ref_gsd)
        add("nonrigid", "Non-rigid correction",
            "A homography is exact for a flat scene and a pin-hole camera; a push-broom camera with platform "
            "jitter over rough terrain is neither. Left: the smooth displacement field fitted on top of the "
            "homography (it is kept only when it predicts held-out tiles better). Right: per-match error "
            "before and after it.", "Diagnostics")

    if H_prior is not None:
        offsets = prior_offsets(H_prior, anchors_src, ref_xy[anchor_idx])
        predicted_local = apply_homography(H_prior, anchors_src) - off
        _render_prior(viz_dir / "prior.png", predicted_local, anchors_ref_local, offsets, (ref_h, ref_w))
        add("prior", "Agreement with the control-grid prior",
            "Independent of the matcher: blue circles are where the product's own geolocation grid says each "
            "anchor should land, red dots where the match actually landed. A real fit gives short, similar "
            "arrows (a steady pointing offset); a wrong one scatters.", "Diagnostics")

    # --- numbers
    centre = (src_w / 2, src_h / 2)
    checks = health_checks(H, src_xy, ref_xy, rmse, expected_scale, H_prior, centre, reference_gsd=ref_gsd)
    decomp = decompose_transform(H, centre)
    scales = [local_scale(H_local, x, y) for x, y in ((0, 0), (src_w, 0), (0, src_h), (src_w, src_h))]
    failed = [c for c in checks if c["ok"] is False]
    params = [
        {"label": "AXIS SCALES", "value": f"{decomp['sigma_major']:.2f} / {decomp['sigma_minor']:.3f}"},
        {"label": "EXPECTED SCALE (GSD RATIO)", "value": f"{expected_scale:.2f}" if expected_scale else "—"},
        {"label": "ROTATION", "value": f"{decomp['rotation_deg']:.1f}°"},
        {"label": "SCALE ACROSS THE STRIP", "value": f"{min(scales):.2f} .. {max(scales):.2f}"},
        {"label": "DISTINCT ANCHORS", "value": f"{n_anchors} of {len(rows)} counted"},
    ]
    if metrics.get("structure"):
        params.append({"label": "MATCHING REPRESENTATION", "value": str(metrics["structure"])})
    if model.field_fn is not None:
        rms_m, held_m = metrics.get("nonrigid_field_rms_m"), metrics.get("heldout_rmse_m")
        text = ", ".join(x for x in (f"rms {rms_m:.1f} m" if rms_m is not None else None,
                                     f"held-out error {held_m:.1f} m" if held_m is not None else None) if x)
        params.append({"label": "BEYOND THE HOMOGRAPHY", "value": text or "applied"})
    par = (metrics.get("nonrigid") or {}).get("parallax")
    if par:
        exp = par.get("alpha_prior") or [None, None]
        params.append({"label": "DEM PARALLAX (tan of view angle)",
                       "value": f"fitted {par.get('alpha_along', 0):+.2f} along, {par.get('alpha_cross', 0):+.2f} across"
                                + (f"; label says {abs(exp[0]):.2f}, {abs(exp[1] or 0):.2f}" if exp[0] is not None else "")})
    if ctx.relit is not None:
        params.append({"label": "RE-LIT DEM LAYER", "value": "used"})
    if ctx.decimation > 1.05:
        params.append({"label": "SOURCE READ AT", "value": f"1/{ctx.decimation:.0f} resolution"})
    return {
        "version": VIZ_VERSION,
        "verdict": "suspect" if failed else "ok",
        "summary": (
            f"{len(failed)} of {len([c for c in checks if c['ok'] is not None])} checks failed — "
            "this fit should not be trusted." if failed else "All sanity checks passed."
        ),
        "checks": checks,
        "params": params,
        "items": items,
    }


def generate_visualizations(config: dict, run_id: str, force: bool = False) -> dict:
    """Renders (or loads cached) viz/ images + manifest for a run. Assumes the
    process cwd is algo/, like pipeline.run, so config paths resolve."""
    out_dir = Path(config["evaluation"]["output_dir"]) / run_id
    viz_dir = out_dir / "viz"
    manifest_path = viz_dir / "manifest.json"
    with _lock:  # the UI may request several images at once; render only once
        if manifest_path.exists() and not force:
            cached = json.loads(manifest_path.read_text())
            if cached.get("version") == VIZ_VERSION:
                return cached
        manifest = _render(config, out_dir, viz_dir)
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return manifest


def viz_image_path(config: dict, run_id: str, name: str) -> Path:
    manifest = generate_visualizations(config, run_id)
    if name not in {item["name"] for item in manifest["items"]}:
        raise FileNotFoundError(f"no visualization named {name!r}")
    return Path(config["evaluation"]["output_dir"]) / run_id / "viz" / f"{name}.png"
