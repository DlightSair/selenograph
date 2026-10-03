"""Prior-guided dense tile matching.

Searching the whole reference for look-alike terrain yields few, clustered and
often wrong anchors, from which one homography would be extrapolated across a
~100 km strip. This matcher instead uses what is already known: the
product's own control grid gives an independent source->reference mapping
(`preprocessing.grid.control_grid_prior_homography`), accurate to a few
hundred metres. With that prior the problem is not "find this crater
anywhere on the Moon" but "measure a small residual shift", which is solved
locally and robustly:

  1. Cover the overlap with a regular grid of tiles.
  2. For each tile, resample the source into the reference frame through the
     current transform and cross-correlate it (zero-mean NCC on an
     illumination-robust structure representation, see `matching.structure`)
     against the reference inside a limited search window. The peak is that
     tile's residual shift.
  3. Fit one homography to *all* tile measurements robustly (MAGSAC).
  4. Repeat with the improved transform and a smaller search window.

Coverage is spread across the whole overlap by construction, and an outlier
tile (featureless plain, no-data, look-alike) is just one voter among many.

Scale handling: each stage works at one *common* ground resolution. The finer of
the two images is block-averaged down to the coarser one (so a 0.26 m OHRC strip
is reduced to the ~4 m of its NAC reference, a 5 m TMC-2 strip to the 100 m of
a WAC reference, and a coarse 100 m IIRS cube leaves a 5 m reference to be
reduced). Either image may be the finer one.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

import cv2
import numpy as np

from algo.geometry.analysis import apply_homography, local_scale
from algo.geometry.model_fit import fit_full_model
from algo.geometry.parallax import parallax_basis
from algo.matching import structure
from algo.matching.match import Match


@dataclass
class Stage:
    down: int  # minimum reference downsample factor for this stage
    tile: int  # template size, in this stage's reference pixels
    margin: int  # search radius around the predicted position, same units
    stride: int  # tile spacing
    translation_only: bool = False  # coarse capture stage: only update a global shift from it
    dense: bool = False  # final high-density pass: tighter NCC bar (many tiles, so be picky)
    min_ncc: float | None = None  # override of the configured minimum correlation for this stage
    select: bool = False  # re-decide the correlation surface here, by how self-consistent each candidate's tiles are


@dataclass
class TileMatch:
    source_xy: tuple[float, float]  # source-crop coords (stage resolution)
    reference_xy: tuple[float, float]  # reference-crop-local coords (stage resolution)
    ncc: float
    margin_ratio: float  # ncc - second-best-peak ncc
    shift: tuple[float, float]  # residual shift, reference-crop px


@dataclass
class RefLayer:
    """One reference image on the common reference grid. Several layers (e.g. the LRO image and the
    DEM re-lit with the source's own Sun) are correlated against the same source tile and their
    correlation surfaces are averaged by `weight`."""

    image: np.ndarray
    weight: float = 1.0
    modes: dict[str, float] | None = None  # None: use the matcher's default representation


class SourcePyramid:
    """The source crop at (possibly) several block-averaged resolutions.

    `base` may already be decimated relative to the full-resolution crop (huge OHRC strips are
    read decimated); `base_to_full` maps base pixel coords to full-resolution crop coords. Every
    level returned by `get` carries the matrix mapping *its* pixels to full-resolution crop
    coordinates, so matches can always be reported in the full-resolution frame."""

    def __init__(self, base: np.ndarray, base_to_full: np.ndarray | None = None):
        self.base = base.astype(np.float32) if base.dtype != np.float32 else base
        self.S0 = np.eye(3) if base_to_full is None else np.asarray(base_to_full, dtype=np.float64)
        self._cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    @property
    def shape(self) -> tuple[int, int]:
        return self.base.shape

    @property
    def base_factor(self) -> float:
        return float(self.S0[0, 0])

    def full_size(self) -> tuple[int, int]:
        """(width, height) of the full-resolution crop."""
        h, w = self.base.shape
        return w * self.S0[0, 0], h * self.S0[1, 1]

    def get(self, factor: float) -> tuple[np.ndarray, np.ndarray]:
        """Level whose pixels are ~`factor` full-res pixels wide (never finer than the base)."""
        g = max(1.0, factor / self.base_factor)
        key = int(round(g * 1000))
        if key in self._cache:
            return self._cache[key]
        if g < 1.05:
            out = (self.base, self.S0)
        else:
            h, w = self.base.shape
            ow, oh = max(8, int(round(w / g))), max(8, int(round(h / g)))
            img = cv2.resize(self.base, (ow, oh), interpolation=cv2.INTER_AREA)
            out = (img, self.S0 @ _level_matrix(w / ow, h / oh))
        self._cache[key] = out
        return out


def _level_matrix(fx: float, fy: float) -> np.ndarray:
    """ds pixel i has its centre at (i + .5) * f - .5 in the finer image's pixel coordinates."""
    return np.array([[fx, 0, 0.5 * fx - 0.5], [0, fy, 0.5 * fy - 0.5], [0, 0, 1]], dtype=np.float64)


def _reduce(img: np.ndarray, factor: float) -> tuple[np.ndarray, np.ndarray]:
    """Block-average `img` by `factor` (>= 1); returns (image, matrix mapping its pixels to img pixels)."""
    if factor < 1.05:
        return img, np.eye(3)
    h, w = img.shape
    ow, oh = max(8, int(round(w / factor))), max(8, int(round(h / factor)))
    return cv2.resize(img, (ow, oh), interpolation=cv2.INTER_AREA), _level_matrix(w / ow, h / oh)


def stages_for(reference_gsd: float, reference_shape: tuple[int, int], footprint_min_px: float | None = None) -> list[Stage]:
    if reference_gsd <= 20:  # high-res (NAC-class) reference
        # The capture stage votes with many coarse tiles, so it needs the source footprint to span
        # a few hundred coarse pixels: reduce by up to 8x for 100 km strips, less for small crops.
        extent = min(reference_shape) if footprint_min_px is None else min(min(reference_shape), footprint_min_px)
        coarse_down = int(max(1, min(8, extent // 500)))
        return [
            Stage(down=coarse_down, tile=128, margin=128, stride=64, translation_only=True, min_ncc=0.12),
            # drift correction: a control grid can wander by hundreds of metres along a pass, which a global
            # shift cannot absorb; one affine fit at the same coarse scale (half the search radius) can
            Stage(down=coarse_down, tile=128, margin=64, stride=80, min_ncc=0.10),
            Stage(down=1, tile=384, margin=48, stride=320, select=True),
            Stage(down=1, tile=384, margin=24, stride=256),
            Stage(down=1, tile=128, margin=20, stride=48, dense=True),  # thousands of (overlapping) measurements
        ]
    return [  # coarse (WAC-class) reference: tiles are few reference pixels wide
        Stage(down=1, tile=64, margin=24, stride=48, translation_only=True, min_ncc=0.12),
        Stage(down=1, tile=64, margin=12, stride=32, select=True),
        Stage(down=1, tile=40, margin=8, stride=16, dense=True),
    ]


# structure-representation presets: weight per representation in the (fused) correlation surface
PRESETS: dict[str, dict[str, float]] = {
    "intensity": {"intensity": 1.0},
    "orient": {"orient": 1.0},
    "cfog": {"cfog": 1.0},
    "edges": {"edges": 1.0},
    "fused": {"intensity": 0.5, "cfog": 0.5},
}


# Representations tried by the capture-stage self-check (see match_prior_guided), in tie-break order.
# Measured on Sun-azimuth sweeps (benchmark): intensity is exact while the Sun is within ~30 deg, then
# collapses; gradient magnitude ("edges") keeps finding the right peak up to 180 deg; cfog is the most
# precise when lighting is close and recovers at 180 deg, but fails at 90-120.
DEFAULT_CANDIDATES = ["intensity", "edges", "cfog"]


def resolve_modes(structure_cfg) -> dict[str, float]:
    if isinstance(structure_cfg, dict):
        return dict(structure_cfg)
    if isinstance(structure_cfg, (list, tuple)):
        return {m: 1.0 for m in structure_cfg}
    return dict(PRESETS[structure_cfg]) if structure_cfg in PRESETS else {str(structure_cfg): 1.0}


def _subpixel(res: np.ndarray, px: int, py: int) -> tuple[float, float]:
    fx, fy = float(px), float(py)
    h, w = res.shape
    if 0 < px < w - 1:
        d = res[py, px - 1] - 2 * res[py, px] + res[py, px + 1]
        if abs(d) > 1e-9:
            fx += 0.5 * (res[py, px - 1] - res[py, px + 1]) / d
    if 0 < py < h - 1:
        d = res[py - 1, px] - 2 * res[py, px] + res[py + 1, px]
        if abs(d) > 1e-9:
            fy += 0.5 * (res[py - 1, px] - res[py + 1, px]) / d
    return fx, fy


def _threads() -> int:
    """Worker threads for tile matching (ALGO_THREADS overrides; benchmarks that already fan out over
    processes set it to 1)."""
    env = os.environ.get("ALGO_THREADS")
    return max(1, int(env)) if env else max(1, min(8, (os.cpu_count() or 2) - 2))


def _warp_feat(feat: np.ndarray, Mt: np.ndarray, T: int) -> np.ndarray:
    """Warp a (H, W, K) feature stack into a T x T tile frame (cv2 handles at most 4 channels per call)."""
    K = feat.shape[2]
    parts = [cv2.warpPerspective(np.ascontiguousarray(feat[..., i:i + 4]), Mt, (T, T), flags=cv2.INTER_LINEAR).reshape(T, T, -1)
             for i in range(0, K, 4)]
    return parts[0] if len(parts) == 1 else np.concatenate(parts, axis=2)


_LAT_STEP = 32  # reference-ds px between lattice nodes of the inverse map


def _inverse_lattice(H: np.ndarray, field, S_src: np.ndarray, S_ref: np.ndarray, ref_shape: tuple[int, int]) -> np.ndarray:
    """For lattice nodes of the stage-resolution reference image, the stage-resolution source coordinate that
    the current model (homography + displacement field) maps onto them: (n_y, n_x, 2) float32. The tile
    templates are then resampled through this map, so a tile is built along the model's curved geometry
    instead of a plane -- what lets a stage measure *residuals* around a non-rigid prior."""
    h, w = ref_shape
    nx, ny = int(np.ceil(w / _LAT_STEP)) + 2, int(np.ceil(h / _LAT_STEP)) + 2
    gx, gy = np.meshgrid(np.arange(nx) * float(_LAT_STEP), np.arange(ny) * float(_LAT_STEP))
    q = apply_homography(S_ref, np.stack([gx.ravel(), gy.ravel()], axis=1))
    d1 = np.asarray(field(q))
    d2 = np.asarray(field(q - d1))  # one fixed-point refinement of p + d(p) = q
    x_full = apply_homography(np.linalg.inv(H), q - d2)
    return apply_homography(np.linalg.inv(S_src), x_full).reshape(ny, nx, 2).astype(np.float32)


def _lat_sample(lat: np.ndarray, x: float, y: float) -> np.ndarray:
    from scipy.ndimage import map_coordinates

    c = [[y / _LAT_STEP], [x / _LAT_STEP]]
    return np.array([map_coordinates(lat[..., k], c, order=1, mode="nearest")[0] for k in (0, 1)])


def _remap_feat(feat: np.ndarray, mx: np.ndarray, my: np.ndarray) -> np.ndarray:
    T = mx.shape[0]
    K = feat.shape[2]
    parts = [cv2.remap(np.ascontiguousarray(feat[..., i:i + 4]), mx, my, cv2.INTER_LINEAR).reshape(T, T, -1) for i in range(0, K, 4)]
    return parts[0] if len(parts) == 1 else np.concatenate(parts, axis=2)


def _tile_pass(src: np.ndarray, layers: list[RefLayer], H: np.ndarray, st: Stage, modes: dict[str, float], min_ncc: float,
               lat: np.ndarray | None = None, valid_img: np.ndarray | None = None):
    """Match every tile. `H` maps `src` coords -> `ref` coords (both already at stage resolution).
    `layers` are reference images on the same grid; the first one decides tile validity. `lat`
    (optional) is the inverse lattice of a non-rigid prior (see `_inverse_lattice`): tiles are then
    resampled through it instead of through the homography alone."""
    ref = layers[0].image if valid_img is None else valid_img  # decides which tiles are usable (has data)
    h, w = ref.shape
    sh, sw = src.shape
    M = st.margin
    corners = apply_homography(H, np.array([[0, 0], [sw, 0], [sw, sh], [0, sh]], dtype=float))
    xmin, ymin = np.maximum(corners.min(axis=0), 0).astype(int)
    xmax, ymax = np.minimum(corners.max(axis=0), [w, h]).astype(int)
    # tiles stay inside the (possibly narrow) source image (<= ~60% of its shorter side) and small enough that
    # the footprint holds a few of them (<= 40% of its shorter side): a stage tuned for a 100 km strip would
    # otherwise place one or two tiles on a 5 km scene and have nothing to fit
    footprint_min = max(min(xmax - xmin, ymax - ymin), 1)
    T = int(max(32, min(st.tile, (min(sh, sw) * 0.6) // 8 * 8, (footprint_min * 0.4) // 8 * 8)))
    if lat is not None:  # the displacement field can push the footprint past the homography's corners
        xmin, ymin = max(0, xmin - M), max(0, ymin - M)
        xmax, ymax = min(w, xmax + M), min(h, ymax + M)
    ones = np.ones(src.shape, np.uint8)
    inv = np.linalg.inv(H)
    if lat is not None:
        lat_x, lat_y = np.ascontiguousarray(lat[..., 0]), np.ascontiguousarray(lat[..., 1])
    rad = max(4, T // 24)
    nsig = max(6.0, 0.03 * T)
    out: list[TileMatch] = []
    attempted = 0
    stride = max(1, int(round(st.stride * T / st.tile)))

    # Features of the whole (stage-resolution) images are computed once and sliced/warped per tile: tiles
    # overlap heavily (stride << window), so recomputing them per tile repeats the same work ~10x.
    layer_modes = [layer.modes or modes for layer in layers]
    src_modes = {m for lm in layer_modes for m in lm}
    n_ref = sum(structure.channels(m) for lm in layer_modes for m in lm)
    n_src = sum(structure.channels(m) for m in src_modes)
    cached = (ref.size * n_ref + src.size * n_src) * 4 < 2.0e9
    if cached:
        src_f = {m: structure.features(src, m, norm_sigma=nsig) for m in src_modes}
        ref_f = [{m: structure.features(layer.image, m, norm_sigma=nsig) for m in lm} for layer, lm in zip(layers, layer_modes)]

    def match_tile(pos):
        """One tile: returns (attempted, TileMatch | None). Pure function of its inputs, so tiles can run on threads
        (OpenCV and NumPy release the GIL in the heavy calls)."""
        x0, y0 = pos
        # search window around the predicted position, clipped at the reference border
        wx0, wy0 = max(0, x0 - M), max(0, y0 - M)
        wx1, wy1 = min(w, x0 + T + M), min(h, y0 + T + M)
        win = ref[wy0:wy1, wx0:wx1]
        if (win > 0).mean() < 0.9:
            return 0, None
        if lat is None:
            Mt = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], dtype=np.float64) @ H
            valid = cv2.warpPerspective(ones, Mt, (T, T), flags=cv2.INTER_NEAREST)
            if valid.mean() < 0.98:
                return 0, None
            tmpl = cv2.warpPerspective(src, Mt, (T, T), flags=cv2.INTER_LINEAR)
            warp_feat = lambda f: _warp_feat(f, Mt, T)  # noqa: E731
        else:
            cx_, cy_ = np.meshgrid((np.arange(T, dtype=np.float32) + x0) / _LAT_STEP, (np.arange(T, dtype=np.float32) + y0) / _LAT_STEP)
            mx = cv2.remap(lat_x, cx_, cy_, cv2.INTER_LINEAR)
            my = cv2.remap(lat_y, cx_, cy_, cv2.INTER_LINEAR)
            valid = cv2.remap(ones, mx, my, cv2.INTER_NEAREST)
            if valid.mean() < 0.98:
                return 0, None
            tmpl = cv2.remap(src, mx, my, cv2.INTER_LINEAR)
            warp_feat = lambda f: _remap_feat(f, mx, my)  # noqa: E731
        if tmpl.std() < 1e-6 or win.std() < 1e-6:
            return 0, None

        res = None
        total_w = 0.0
        ft_cache = {m: warp_feat(src_f[m]) for m in src_modes} if cached else {}
        for li, layer in enumerate(layers):
            lmodes = layer_modes[li]
            if cached:
                fw = {m: ref_f[li][m][wy0:wy1, wx0:wx1] for m in lmodes}
            else:
                lwin = win if layer.image is ref else layer.image[wy0:wy1, wx0:wx1]
                fw = {m: structure.features(lwin, m, norm_sigma=nsig) for m in lmodes}
                for m in lmodes:
                    if m not in ft_cache:
                        ft_cache[m] = structure.features(tmpl, m, norm_sigma=nsig)
            r = structure.fused_response(fw, ft_cache, lmodes) * layer.weight
            res = r if res is None else res + r
            total_w += layer.weight
        res = res / total_w
        _, p1, _, (px, py) = cv2.minMaxLoc(res)
        if p1 < min_ncc:
            return 1, None
        masked = res.copy()
        masked[max(0, py - rad):py + rad + 1, max(0, px - rad):px + rad + 1] = -1
        p2 = float(masked.max())
        fx, fy = _subpixel(res, px, py)
        dx, dy = wx0 + fx - x0, wy0 + fy - y0
        cx, cy = x0 + T / 2, y0 + T / 2
        source_xy = apply_homography(inv, np.array([[cx, cy]]))[0] if lat is None else _lat_sample(lat, cx, cy)
        return 1, TileMatch(tuple(source_xy), (cx + dx, cy + dy), float(p1), float(p1 - p2), (dx, dy))

    positions = [(x0, y0) for y0 in range(max(0, ymin), min(h - T, ymax - T) + 1, stride)
                 for x0 in range(max(0, xmin), min(w - T, xmax - T) + 1, stride)]
    workers = _threads()
    if workers > 1 and len(positions) >= 48:
        with ThreadPoolExecutor(workers) as pool:
            results = list(pool.map(match_tile, positions, chunksize=8))
    else:
        results = [match_tile(pos) for pos in positions]
    for att, tm in results:
        attempted += att
        if tm is not None:
            out.append(tm)
    return out, attempted


def _robust_translation(shifts: np.ndarray, radius: float) -> tuple[np.ndarray | None, int]:
    """Mode of a set of 2D shifts: the shift with the most neighbours within `radius`,
    averaged. Returns (shift, number of agreeing tiles)."""
    if len(shifts) == 0:
        return None, 0
    d = np.hypot(shifts[:, None, 0] - shifts[None, :, 0], shifts[:, None, 1] - shifts[None, :, 1])
    counts = (d <= radius).sum(axis=1)
    best = int(np.argmax(counts))
    return shifts[d[best] <= radius].mean(axis=0), int(counts[best])


def _dense_bar(configured: float | None, prev_median_ncc: float | None, fallback: float = 0.3) -> float:
    """Correlation bar for the many-tile pass: 80% of the previous stage's median, floored at 0.2 (or at
    the fine-stage bar when that is lower: gradient-based representations peak lower than intensity).
    A fixed bar does not suit all scenes (typical peak correlations range from ~0.3 to ~0.5)."""
    if configured is not None:
        return configured
    floor = min(0.2, fallback)
    return max(floor, 0.8 * prev_median_ncc) if prev_median_ncc else max(floor, fallback)


def _capture_vote(tiles: list[TileMatch], S_ref, st: Stage, b: float):
    """Global-shift consensus of a capture-stage tile pass: (shift in full ref px, agreeing tiles, median ncc of those)."""
    ref_full = apply_homography(S_ref, np.array([t.reference_xy for t in tiles]))
    pred_full = apply_homography(S_ref, np.array([np.array(t.reference_xy) - t.shift for t in tiles]))
    shifts = ref_full - pred_full
    radius = max(6.0, 0.08 * st.margin * b)
    d = np.hypot(shifts[:, None, 0] - shifts[None, :, 0], shifts[:, None, 1] - shifts[None, :, 1])
    counts = (d <= radius).sum(axis=1)
    best = int(np.argmax(counts))
    members = d[best] <= radius
    return shifts[members].mean(axis=0), int(counts[best]), float(np.median([t.ncc for t, m in zip(tiles, members) if m]))


def _robust_stage_fit(src_full: np.ndarray, ref_full: np.ndarray, H_prev: np.ndarray, thr: float, field=None):
    """Robust update of the working homography from one stage's tile measurements.

    MAGSAC on a raw homography is unreliable for narrow push-broom strips (IIRS is 250 px wide, so
    4-point samples are nearly collinear and almost every sample is degenerate). The prior already
    carries the perspective, so the *correction* is small: fit it as an affine map in the reference
    frame (6 well-conditioned parameters, RANSAC), and only upgrade to a full least-squares
    homography on the inliers when they span the strip in both directions and it clearly helps.
    With a displacement `field` the measured positions have it removed first (the field is the
    non-rigid part of the model; the homography is what is being corrected).
    Returns (H_new, inlier mask) or (None, None)."""
    pred = apply_homography(H_prev, src_full)
    if field is not None:
        ref_full = ref_full - np.asarray(field(pred))
    A, inl = cv2.estimateAffine2D(
        pred.astype(np.float32), ref_full.astype(np.float32), method=cv2.RANSAC,
        ransacReprojThreshold=thr, maxIters=4000, confidence=0.995, refineIters=15,
    )
    if A is None or inl is None:
        return None, None
    mask = inl.ravel().astype(bool)
    H_new = np.vstack([A, [0.0, 0.0, 1.0]]) @ H_prev
    pts = src_full[mask]
    if mask.sum() >= 40:
        spans = np.ptp(pts, axis=0)
        if spans.min() / max(spans.max(), 1.0) > 0.25:
            Hh, _ = cv2.findHomography(pts.astype(np.float32), ref_full[mask].astype(np.float32), 0)
            if Hh is not None:
                def rms(Hx):
                    return float(np.sqrt(np.mean(np.sum((apply_homography(Hx, pts) - ref_full[mask]) ** 2, axis=1))))
                if rms(Hh) < 0.9 * rms(H_new):
                    H_new = Hh
    return H_new, mask


def _mode_cost(modes: dict[str, float]) -> int:
    return sum(structure.channels(m) for m in modes)


def _assign_cost(assign, layers_ds: list[RefLayer]) -> float:
    """Feature pixels (image size x channels) a correlation surface needs: what a stage must hold in memory and correlate."""
    return float(sum(layers_ds[li].image.size * _mode_cost(modes) for li, modes in assign))


def _assign_layers(assign, layers_ds: list[RefLayer]) -> list[RefLayer]:
    """The reference layers selected by `assign` = [(layer index, modes), ...], keeping each layer's weight."""
    return [RefLayer(layers_ds[li].image, layers_ds[li].weight, modes) for li, modes in assign]


def _capture(src_ds, layers_ds, H_ds, S_ref, st, b, candidates, min_ncc, lat=None, max_members: int = 2, tol: float = 0.08):
    """Capture-stage vote over (reference layer x representation) candidates.

    Every candidate correlates the source against ONE layer in ONE representation and gets the fraction of
    tiles that agree on a single global shift. Averaging layers blindly is wrong: a reference image lit
    from another direction and a DEM re-lit with the source's Sun disagree, and the average inherits the
    image's bias. So the members of the final correlation surface are chosen by their own agreement:
    all candidates within `tol` of the best, cheapest representation first, at most `max_members`.

    Returns (best, scores); best = (agree fraction, label, assignment, tiles, attempted, shift, agree,
    median ncc, ranked single candidates) or None. `assignment` is [(layer index, modes), ...]."""
    bar = st.min_ncc if st.min_ncc is not None else min_ncc
    valid = layers_ds[0].image
    singles = []
    scores = {}
    for li, layer in enumerate(layers_ds):
        for name, cand in candidates:
            label = name if li == 0 else f"{name}@layer{li}"
            tl, att = _tile_pass(src_ds, [RefLayer(layer.image, layer.weight, cand)], H_ds, st, cand, bar, lat, valid_img=valid)
            if len(tl) < 4:
                scores[label] = {"tiles": len(tl), "attempted": att, "agree": 0}
                continue
            shift, agree, med = _capture_vote(tl, S_ref, st, b)
            scores[label] = {"tiles": len(tl), "attempted": att, "agree": agree, "median_ncc": round(med, 3)}
            singles.append({"frac": agree / max(att, 1), "label": label, "li": li, "modes": cand, "tiles": tl, "att": att,
                            "shift": shift, "agree": agree, "med": med})
    if not singles:
        return None, scores
    top = max(s["frac"] for s in singles)
    eligible = sorted((s for s in singles if s["frac"] >= top - tol), key=lambda s: (_mode_cost(s["modes"]), -s["frac"]))[:max_members]
    per_layer: dict[int, dict[str, float]] = {}
    for s in eligible:
        per_layer.setdefault(s["li"], {}).update(s["modes"])
    assign = sorted(per_layer.items())
    label = "+".join(s["label"] for s in eligible)
    ranked = [(s["label"], [(s["li"], s["modes"])]) for s in sorted(singles, key=lambda s: -s["frac"])]
    if len(eligible) == 1:
        s = eligible[0]
        return (s["frac"], label, assign, s["tiles"], s["att"], s["shift"], s["agree"], s["med"], ranked), scores
    tl, att = _tile_pass(src_ds, _assign_layers(assign, layers_ds), H_ds, st, {}, bar, lat, valid_img=valid)
    if len(tl) < 4:  # the fused surface lost the peak: fall back to the best single candidate
        s = max(singles, key=lambda s: s["frac"])
        return (s["frac"], s["label"], [(s["li"], s["modes"])], s["tiles"], s["att"], s["shift"], s["agree"], s["med"], ranked), scores
    shift, agree, med = _capture_vote(tl, S_ref, st, b)
    scores[label] = {"tiles": len(tl), "attempted": att, "agree": agree, "median_ncc": round(med, 3), "fused": True}
    return (agree / max(att, 1), label, assign, tl, att, shift, agree, med, ranked), scores


_RESCUE_ROTATIONS = (0.0, 3.0, -3.0, 6.0, -6.0, 10.0, -10.0)
_RESCUE_SCALES = (1.0, 0.92, 1.08)


def _rescue_capture_one(pyr, layers32, H, reference_gsd, candidates, min_ncc):
    """Capture for a prior that is badly wrong. The normal capture stage searches a few km; when the
    control grid is further off than that (or rotated / mis-scaled), widen the search: coarser
    working resolution (so the same window reaches 4-8x further) and a small set of rotation x scale
    hypotheses about the source centre. A hypothesis is accepted only when many tiles agree on one
    shift AND it clearly beats the runner-up (a lucky noise cluster does not)."""
    ref32 = layers32[0].image
    full_w, full_h = pyr.full_size()
    cx, cy = full_w / 2, full_h / 2
    results = []
    # the two coarsest working resolutions that still leave >= 150 reference px (a 100 m WAC crop is only a few hundred
    # pixels wide, so its widest search is at 1-2x; a 100 km NAC strip reaches 16-32x)
    downs = [d for d in (1, 2, 4, 8, 16, 32) if min(ref32.shape) / d >= 150][-2:]
    for down in downs:
        scale0 = local_scale(H, cx, cy)
        b = float(max(down, round(scale0)) if scale0 > 1.5 else down)
        a = max(1.0, b / scale0)
        src_ds, S_src = pyr.get(a)
        ref_ds, S_ref = _reduce(ref32, b)
        if min(ref_ds.shape) < 160 or min(src_ds.shape) < 80:
            continue
        layers_ds = [RefLayer(ref_ds, layers32[0].weight, layers32[0].modes)] + [
            RefLayer(_reduce(l.image, b)[0], l.weight, l.modes) for l in layers32[1:]
        ]
        st = Stage(down=int(b), tile=64, margin=160, stride=32, translation_only=True, min_ncc=0.10)
        for rot in _RESCUE_ROTATIONS:
            for sc in _RESCUE_SCALES:
                th = np.radians(rot)
                R = np.array([[sc * np.cos(th), -sc * np.sin(th), 0], [sc * np.sin(th), sc * np.cos(th), 0], [0, 0, 1.0]])
                Tc = np.array([[1, 0, cx], [0, 1, cy], [0, 0, 1.0]])
                Hh = H @ Tc @ R @ np.linalg.inv(Tc)
                H_ds = np.linalg.inv(S_ref) @ Hh @ S_src
                best, _ = _capture(src_ds, layers_ds, H_ds, S_ref, st, b, candidates, min_ncc, max_members=1)
                if best is not None:
                    frac, name, assign, _, att, shift, agree, med = best[:8]
                    results.append({"agree": agree, "frac": frac, "attempted": att, "name": name, "assign": assign, "rot": rot,
                                    "scale": sc, "down": down, "H": np.array([[1, 0, shift[0]], [0, 1, shift[1]], [0, 0, 1.0]]) @ Hh})
    if not results:
        return None, None
    results.sort(key=lambda r: (-r["agree"], -r["frac"]))
    top = results[0]
    # a hypothesis only counts as a rival if it implies a genuinely different placement of the strip
    # (neighbouring rotation/scale steps that land within half a tile are the same solution)
    box = np.array([[0, 0], [full_w, 0], [full_w, full_h], [0, full_h]], dtype=float)
    top_c = apply_homography(top["H"], box)
    far = 0.5 * 64 * top["down"]
    rivals = [r for r in results[1:] if np.abs(apply_homography(r["H"], box) - top_c).max() > far]
    runner_up = rivals[0]["agree"] if rivals else 0
    if top["agree"] < max(6, 0.4 * top["attempted"]) or top["agree"] < 1.5 * max(runner_up, 1):
        return None, {"hypotheses_tried": len(results), "best_agree": top["agree"], "runner_up_agree": runner_up}
    # refine: the hypothesis grid is coarse (3 deg / 8%), so fit a homography to the tile matches themselves,
    # first at the working resolution then at twice the resolution
    H_cur = top["H"]
    for down in (top["down"], max(1, top["down"] // 2)):
        scale = local_scale(H_cur, cx, cy)
        b = float(max(down, round(scale)) if scale > 1.5 else down)
        a = max(1.0, b / scale)
        src_ds, S_src = pyr.get(a)
        ref_ds, S_ref = _reduce(ref32, b)
        layers_ds = [RefLayer(ref_ds, layers32[0].weight, layers32[0].modes)] + [
            RefLayer(_reduce(l.image, b)[0], l.weight, l.modes) for l in layers32[1:]
        ]
        st = Stage(down=int(b), tile=64, margin=96, stride=32, translation_only=True, min_ncc=0.10)
        tl, _att = _tile_pass(src_ds, _assign_layers(top["assign"], layers_ds), np.linalg.inv(S_ref) @ H_cur @ S_src, st, {}, 0.10,
                              valid_img=ref_ds)
        if len(tl) < 8:
            break
        s_full = apply_homography(S_src, np.array([t_.source_xy for t_ in tl]))
        r_full = apply_homography(S_ref, np.array([t_.reference_xy for t_ in tl]))
        Hn, mask = _robust_stage_fit(s_full, r_full, H_cur, 1.5 * b)
        if Hn is not None and mask.sum() >= max(8, 0.5 * len(tl)):
            H_cur = Hn
    top = {**top, "H": H_cur}
    return top, {"hypotheses_tried": len(results), "rotation_deg": top["rot"], "scale": top["scale"], "down": top["down"],
                 "agree": top["agree"], "runner_up_agree": runner_up}


def _rescue_capture(pyr, layers32, H, reference_gsd, candidates, min_ncc):
    """Run the wide search once per representation (in order) and accept the first that passes its own
    consensus + rival test: mixing representations in one pool gives a false cluster more chances to compete
    with the true one."""
    last = None
    for cand in candidates:
        top, info = _rescue_capture_one(pyr, layers32, H, reference_gsd, [cand], min_ncc)
        if top is not None:
            return top, {**info, "representation": cand[0]}
        last = info or last
    return None, last


def _reference_coverage(ref: np.ndarray, H: np.ndarray, full_w: float, full_h: float) -> float:
    """Fraction of the source footprint (under the prior) that has reference data at all."""
    f = max(1, int(max(ref.shape) // 1500))
    has = ref[::f, ::f] > 0
    poly = (apply_homography(H, np.array([[0, 0], [full_w, 0], [full_w, full_h], [0, full_h]], dtype=float)) / f).astype(np.int32)
    mask = np.zeros(has.shape, np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    return float((has & (mask > 0)).sum() / max(int(mask.sum()), 1))


def _coverage_note(info: dict) -> str:
    cov = info.get("reference_coverage")
    return f" (the reference has data under only {cov * 100:.0f}% of the strip's footprint)" if cov is not None and cov < 0.6 else ""


def _source_quality_failure(src_img: np.ndarray) -> str | None:
    """A source with no usable signal (permanent shadow, Sun below the horizon) can only produce a
    confident-looking wrong fit; say so up front instead."""
    s = src_img[:: max(1, src_img.shape[0] // 600), :: max(1, src_img.shape[1] // 600)]
    s = s[s > 0] if (s > 0).any() else s
    if s.size == 0:
        return "source crop is empty (all zeros)"
    p1, p995 = np.percentile(s, [1, 99.5])
    if p995 - p1 < 3.0 and np.mean(s) < 4.0:
        return f"source has no usable contrast (mean DN {np.mean(s):.1f}, 1-99.5th percentile range {p995 - p1:.1f}): the strip is in shadow or unlit"
    return None


def match_prior_guided(
    source,
    reference_crop,
    H_prior_local: np.ndarray,
    reference_gsd: float,
    cfg: dict | None = None,
    dem: np.ndarray | None = None,
    expected_view: tuple[float, float] | None = None,
) -> tuple[list[Match], dict]:
    """Returns (matches, info). `source` is an ndarray or a `SourcePyramid`; `reference_crop` an
    ndarray or a list of `RefLayer` (e.g. the LRO image and the DEM re-lit with the source's Sun).
    `H_prior_local` maps full-resolution source-crop pixels to reference-crop-local pixels. Matches
    are (full-resolution source-crop xy, reference-crop-local xy); the caller adds the crop's raster
    offset. `info` records per-stage stats.

    `cfg["structure"]` is a representation name / preset / weights dict, or "auto" (default): every
    (reference layer x representation) candidate runs the coarse capture stage, and the correlation
    surface used from then on is built from the candidates whose tiles agree best on a single global
    shift. That self-check is what makes the matcher usable across illumination: intensity correlation
    wins when the Sun is similar, gradient magnitude when it is not, and a DEM re-lit with the source's
    Sun wins when the reference image was lit from elsewhere.

    Between stages the full model (homography + DEM parallax when `dem` is given + smooth displacement
    field) is refitted and used as the next stage's prior, so a stage measures small residuals around it
    even when terrain parallax or jitter displaces features by far more than that stage's search window."""
    cfg = cfg or {}
    field = None
    parallax_prior = None  # signed (along, cross) tan(view) once the label-parallax check has validated it
    structure_cfg = cfg.get("structure", "auto")
    if structure_cfg == "auto":
        candidates = [(c, resolve_modes(c)) for c in cfg.get("structure_candidates", DEFAULT_CANDIDATES)]
    else:
        candidates = [(str(structure_cfg) if not isinstance(structure_cfg, dict) else "custom", resolve_modes(structure_cfg))]
    min_ncc = cfg.get("min_ncc", 0.25)
    dense_ncc = cfg.get("dense_min_ncc")  # None: adapt to how well the previous stage correlated
    prev_median_ncc = None
    fine_bar = min_ncc
    pyr = source if isinstance(source, SourcePyramid) else SourcePyramid(np.asarray(source))
    layers32 = (
        [RefLayer(l.image.astype(np.float32), l.weight, l.modes) for l in reference_crop]
        if isinstance(reference_crop, (list, tuple))
        else [RefLayer(np.asarray(reference_crop).astype(np.float32))]
    )
    ref32 = layers32[0].image
    full_w, full_h = pyr.full_size()
    H = np.asarray(H_prior_local, dtype=np.float64)
    info: dict = {"stages": [], "structure": candidates[0][1]}
    final: list[Match] = []
    assign: list = [(0, candidates[0][1])]
    ranked: list = []
    bad = _source_quality_failure(pyr.base)
    if bad:
        return [], {**info, "failed": bad}
    info["reference_coverage"] = round(_reference_coverage(ref32, H, full_w, full_h), 3)

    corners = apply_homography(H, np.array([[0, 0], [full_w, 0], [full_w, full_h], [0, full_h]], dtype=float))
    footprint_min = float(min(np.ptp(corners[:, 0]), np.ptp(corners[:, 1])))
    for st in stages_for(reference_gsd, ref32.shape, footprint_min):
        scale = local_scale(H, full_w / 2, full_h / 2)  # reference px per full-res source px
        # common working resolution: reference reduced by b, source by a, with a*scale ~= b
        b = float(max(st.down, round(scale)) if scale > 1.5 else st.down)
        a = max(1.0, b / scale)
        if b > st.down + 0.5:  # a coarse source forced a coarser working resolution: keep the ground size of tiles
            f = st.down / b
            st = replace(st, tile=max(48, int(round(st.tile * f / 8)) * 8), margin=max(12, int(round(st.margin * f))),
                         stride=max(8, int(round(st.stride * f))))
        src_ds, S_src = pyr.get(a)
        ref_ds, S_ref = _reduce(ref32, b)
        layers_ds = [RefLayer(ref_ds, layers32[0].weight, layers32[0].modes)] + [
            RefLayer(_reduce(l.image, b)[0], l.weight, l.modes) for l in layers32[1:]
        ]
        H_ds = np.linalg.inv(S_ref) @ H @ S_src
        lat = _inverse_lattice(H, field, S_src, S_ref, ref_ds.shape) if (field is not None and not st.translation_only) else None

        if st.translation_only:
            best, scores = _capture(src_ds, layers_ds, H_ds, S_ref, st, b, candidates, min_ncc)
            info["capture_candidates"] = scores
            if dem is not None and expected_view is not None and cfg.get("label_parallax", True) and max(expected_view) >= 0.07:
                # The label says the camera looked off-nadir, so over relief the reference (orthorectified) and
                # the source differ by height x tan(view). The sign depends on flight/look conventions, so try
                # both and keep the one the capture tiles agree on; bare matching would see a smeared peak.
                ba, bc = parallax_basis(H, dem, reference_gsd, (full_w / 2, full_h / 2), dem_smooth_px=0.0)
                ea, ec = float(expected_view[0]), float(expected_view[1])
                base_frac = 0.0 if best is None else best[0]
                top = None
                for sa in ((1.0, -1.0) if ea >= 0.07 else (0.0,)):
                    for sc in ((1.0, -1.0) if ec >= 0.07 else (0.0,)):
                        fn = (lambda q, sa=sa, sc=sc: sa * ea * ba(q) + sc * ec * bc(q))
                        lat_c = _inverse_lattice(H, fn, S_src, S_ref, ref_ds.shape)
                        cb, _ = _capture(src_ds, layers_ds, H_ds, S_ref, st, b, candidates, min_ncc, lat_c)
                        if cb is not None and (top is None or cb[0] > top[0][0]):
                            top = (cb, fn, sa, sc)
                if top is not None and top[0][0] > base_frac + 0.1:
                    best, field = top[0], top[1]
                    parallax_prior = (top[2] * ea, top[3] * ec)
                    info["label_parallax"] = {"sign_along": top[2], "sign_cross": top[3], "tan_along": ea, "tan_cross": ec,
                                              "capture_agreement": round(top[0][0], 2), "without": round(base_frac, 2)}
            needs_rescue = best is None or best[6] < max(4, 0.2 * len(best[3]))
            if needs_rescue and cfg.get("rescue", True):
                # the wide search compares ~100 placements; extra (6-channel) representations only add chances for a
                # false consensus, so it uses the single-channel ones
                cheap = [(n, m) for n, m in candidates if _mode_cost(m) == 1] or candidates
                rescued, rinfo = _rescue_capture(pyr, layers32, H, reference_gsd, cheap, min_ncc)
                info["rescue"] = rinfo
                if rescued is not None:
                    H = rescued["H"]  # a much better starting point; run the normal capture from it
                    H_ds = np.linalg.inv(S_ref) @ H @ S_src
                    best, scores = _capture(src_ds, layers_ds, H_ds, S_ref, st, b, candidates, min_ncc)
                    info["capture_candidates"] = scores
                    needs_rescue = best is None or best[6] < max(4, 0.2 * len(best[3]))
            if needs_rescue:
                agree = 0 if best is None else best[6]
                return [], {**info, "failed": (f"no consistent global shift (best agreement {agree} tiles across "
                                               f"{len(candidates) * len(layers32)} layer/representation candidate(s))"
                                               + _coverage_note(info) + "; the reference and the source may share too little structure at this scale")}
            _, name, assign, tiles, attempted, shift, agree, med, ranked = best
            info["structure"] = {lbl: m for lbl, m in zip([name], [assign[0][1]])} if len(assign) == 1 else {"layers": [
                {"layer": li, "modes": m} for li, m in assign]}
            info["structure_selected"] = name
            fine_bar = float(np.clip(0.6 * med, 0.08, min_ncc))
            info["stages"].append({"down": round(b, 2), "source_down": round(a, 2), "tile": st.tile, "attempted": attempted,
                                   "matched": len(tiles), "agreeing_tiles": agree, "global_shift_px": [float(shift[0]), float(shift[1])]})
            H = np.array([[1, 0, shift[0]], [0, 1, shift[1]], [0, 0, 1]]) @ H
            continue

        bar = _dense_bar(dense_ncc, prev_median_ncc, fine_bar) if st.dense else fine_bar
        # the capture-selected correlation surface first; if its tiles do not form a consistent homography
        # (illumination can change across a long strip), try the best single candidates before giving up
        order = [(info.get("structure_selected"), assign)] + [(lbl, asg) for lbl, asg in ranked[:4] if lbl != info.get("structure_selected")]
        # a 6-channel representation on a 60 Mpx crop is minutes of work and gigabytes: stay within a budget,
        # falling back to the cheapest surface when even the preferred one does not fit
        budget = float(cfg.get("max_feature_px", 1.5e8))
        fitting = [(n, a) for n, a in order if _assign_cost(a, layers_ds) <= budget]
        order = fitting or [min(order, key=lambda na: _assign_cost(na[1], layers_ds))]
        oks = []
        sigma = 0.0
        for name, asg in order:
            layers_try = _assign_layers(asg, layers_ds)
            tiles, attempted = _tile_pass(src_ds, layers_try, H_ds, st, {}, bar, lat, valid_img=ref_ds)
            if len(tiles) < 4:
                continue
            src_full = apply_homography(S_src, np.array([t_.source_xy for t_ in tiles]))
            ref_full = apply_homography(S_ref, np.array([t_.reference_xy for t_ in tiles]))
            shifts = np.array([t_.shift for t_ in tiles])
            sigma = float(1.4826 * np.median(np.abs(shifts - np.median(shifts, axis=0))))  # stage px: tile-measurement noise
            fit_thr = float(np.clip(3.0 * sigma * b, 3.0, 12.0 * max(1.0, b ** 0.5)))  # reference px
            Hn, mask = _robust_stage_fit(src_full, ref_full, H, fit_thr, field)
            n_in = int(mask.sum()) if mask is not None else 0
            if Hn is None or n_in < max(4, 0.3 * len(tiles)):
                continue
            # self-consistency of the accepted measurements: scatter of the inlier residuals about the fitted model
            pred = apply_homography(Hn, src_full[mask])
            if field is not None:
                pred = pred + np.asarray(field(pred))
            rms = float(np.sqrt(np.mean(np.sum((pred - ref_full[mask]) ** 2, axis=1))))
            oks.append({"name": name, "asg": asg, "n_in": n_in, "rms": rms, "rec": (n_in, name, asg, tiles, attempted, src_full, ref_full, Hn, sigma, fit_thr, mask)})
            if not st.select:
                break  # the preferred surface is consistent; no need to look further
        chosen = None
        if oks:
            if st.select:
                # An agreement vote cannot see a *biased* surface (a reference lit from another direction shifts every
                # edge by a few pixels, which is below a coarse tile's tolerance). Fine tiles can: the scatter of their
                # residuals is larger. Keep the capture's choice unless another surface is clearly more self-consistent.
                best_rms = min(o["rms"] for o in oks)
                pref = next((o for o in oks if o["name"] == order[0][0]), None)
                pick = pref if (pref is not None and pref["rms"] <= 1.25 * best_rms + 0.05) else min(oks, key=lambda o: (o["rms"], -o["n_in"]))
                info["selection"] = [{"surface": o["name"], "inliers": o["n_in"], "residual_rms_px": round(o["rms"], 3)} for o in oks]
            else:
                pick = oks[0]
            chosen = pick["rec"]
        stage_info = {"down": round(b, 2), "source_down": round(a, 2), "tile": st.tile, "bar": round(bar, 3)}
        if chosen is None:
            info["stages"].append({**stage_info, "attempted": attempted, "matched": len(tiles), "fit_inliers": 0,
                                   "tile_noise_px": round(float(sigma), 2)})
            return [], {**info, "failed": (
                f"stage {len(info['stages'])}: the {len(tiles)} tile measurements are not consistent with one transform "
                f"(too few agree); the prior may be wrong or the images too dissimilar" + _coverage_note(info))}
        n_in, name, asg, tiles, attempted, src_full, ref_full, Hn, sigma, fit_thr, in_mask = chosen
        if name != info.get("structure_selected"):
            info.setdefault("structure_switched", []).append({"stage": len(info["stages"]) + 1, "from": info.get("structure_selected"), "to": name})
            info["structure_selected"] = name
            assign = asg
        info["stages"].append({**stage_info, "attempted": attempted, "matched": len(tiles), "fit_inliers": n_in,
                               "tile_noise_px": round(float(sigma), 2), "fit_threshold_px": round(fit_thr, 2),
                               "non_rigid_prior": field is not None})
        prev_median_ncc = float(np.median([t_.ncc for t_ in tiles]))
        H = Hn
        final = [Match(tuple(s), tuple(r), t_.ncc) for s, r, t_ in zip(src_full, ref_full, tiles)]
        if not st.dense and cfg.get("progressive_model", True):
            # refit the full model on this stage's inliers: it becomes the prior of the next stage
            conf = np.array([t_.ncc for t_ in tiles])
            mdl, _ = fit_full_model(
                src_full, ref_full, conf, in_mask, reference_gsd, (full_w, full_h), dem=dem, expected_view=expected_view,
                use_nonrigid=bool(cfg.get("nonrigid", True)), use_parallax=bool(cfg.get("parallax", True)),
                cell=max(48.0, st.stride * b), thr_base=fit_thr, loose=fit_thr, iterations=1, seed_H=Hn,
                dem_smooth_px=0.3 * st.tile * b, parallax_prior=parallax_prior,
            )
            if mdl is not None:
                H = mdl.H
                nr_state = str(mdl.info.get("nonrigid", ""))
                if mdl.field_fn is not None or not nr_state.startswith("skipped"):
                    field = mdl.field_fn
                info["stages"][-1]["model_after"] = {"field": mdl.field_fn is not None, "parallax": bool(mdl.info.get("parallax"))}

    if not final:
        return [], {**info, "failed": "no fine stage ran"}
    info["final_homography"] = H.tolist()
    if parallax_prior is not None:
        info["parallax_prior"] = list(parallax_prior)
    return final, info
