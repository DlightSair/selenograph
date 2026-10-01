"""Stage 3 (auxiliary) -- crater-constellation matcher.

Repetitive cratered terrain is exactly what starves LoFTR/ORB (CLAUDE.md's
"known quality ceiling"): small craters/rocks look alike in many places, so
area-based patch matching finds locally-plausible but globally-inconsistent
correspondences. This matcher turns that structure into an asset instead of
a liability, following crater-pattern matching as used for lunar/planetary
terrain-relative navigation (Christian, Derksen & Watkins 2021, "Lunar
Crater Identification in Digital Images", arXiv:2009.01228): crater rims are
a geometric primitive -- roughly illumination-invariant, unlike pixel
intensity -- so matching the *relative arrangement* of several craters is
far more discriminative on self-similar terrain than matching any single
crater's appearance.

Simplified relative to the literature in two ways (both documented
trade-offs, not oversights):
  - Craters are detected as generic local-intensity-extrema blobs, not
    validated via rim-ellipse fitting or sun-angle-aware shadow/highlight
    pairing -- the reference is a pre-blended QuickMap mosaic with no
    single sun angle (preprocessing.illumination's docstring), so a
    shadow-aware detector could only ever run on the source side anyway.
  - Matching uses similarity-invariant (scale+rotation) constellation
    signatures -- affine skew between the two viewpoints is assumed small
    at the AOI scale, not corrected for -- rather than full projective
    conic invariants.

Blob count must be capped directly (`num_peaks`), not just thresholded: an
absolute LoG-response threshold proved wildly scale-dependent on real data
(thousands of "blobs" on a single tile at thresholds that looked reasonable
on paper), which drowns the constellation matcher's ratio test in noise and
defeats the whole point of using craters as a *sparse, discriminative*
primitive. Capping to the top-N local maxima/minima by intensity gives a
predictable, tunable blob count regardless of a tile's texture.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.exposure import equalize_adapthist
from skimage.feature import peak_local_max

from algo.matching.learned import Match

_NUM_NEIGHBORS = 4  # constellation size: self + 4 nearest neighbours
_RATIO_TEST = 0.85
_NUM_PEAKS = 40  # per polarity (bright + dark), per tile
_MIN_DISTANCE = 8  # px, minimum separation between detected peaks
_SMOOTH_SIGMA = 2  # px, Gaussian pre-smoothing so peaks are crater-scale, not pixel noise


def _detect_blobs(tile: np.ndarray, cfg: dict) -> np.ndarray:
    """Candidate crater centres as (row, col): the top `num_peaks` brightest
    and darkest local extrema (sunlit rims and shadowed floors/walls -- either
    can dominate depending on sun geometry), after smoothing to crater scale."""
    norm = tile.astype(np.float64)
    span = norm.max() - norm.min()
    norm = (norm - norm.min()) / (span if span > 0 else 1.0)
    contrast = equalize_adapthist(norm, clip_limit=0.02)
    smoothed = gaussian_filter(contrast, sigma=cfg.get("smooth_sigma", _SMOOTH_SIGMA))

    kwargs = dict(
        min_distance=cfg.get("min_distance", _MIN_DISTANCE),
        num_peaks=cfg.get("num_peaks", _NUM_PEAKS),
    )
    bright = peak_local_max(smoothed, **kwargs)
    dark = peak_local_max(-smoothed, **kwargs)
    if len(bright) and len(dark):
        return np.vstack([bright, dark]).astype(np.float64)
    return (bright if len(bright) else dark).astype(np.float64)


def _constellation_signatures(blobs: np.ndarray) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    """For each blob, a scale+rotation-invariant descriptor of its
    `_NUM_NEIGHBORS` nearest neighbours: length ratios and angle offsets
    relative to the nearest one -- a local constellation signature, the
    same idea as triangle-ratio star-pattern identification."""
    n = len(blobs)
    if n < _NUM_NEIGHBORS + 1:
        return None, None

    centers = blobs[:, :2]
    signatures = np.zeros((n, 3 * (_NUM_NEIGHBORS - 1)))
    for i in range(n):
        deltas = centers - centers[i]
        dists = np.linalg.norm(deltas, axis=1)
        order = np.argsort(dists)
        order = order[order != i][:_NUM_NEIGHBORS]

        nn_deltas = deltas[order]
        nn_dists = dists[order]
        d1 = nn_dists[0] if nn_dists[0] > 1e-6 else 1e-6
        theta1 = np.arctan2(nn_deltas[0, 0], nn_deltas[0, 1])

        feats = []
        for j in range(1, _NUM_NEIGHBORS):
            r = nn_dists[j] / d1
            alpha = np.arctan2(nn_deltas[j, 0], nn_deltas[j, 1]) - theta1
            feats.extend([r, np.cos(alpha), np.sin(alpha)])
        signatures[i] = feats

    return centers, signatures


def match_crater(level, matching_cfg) -> list[Match]:
    cfg = matching_cfg.get("crater", {})
    source_blobs = _detect_blobs(level.source_tile, cfg)
    reference_blobs = _detect_blobs(level.reference_tile, cfg)

    src_centers, src_sigs = _constellation_signatures(source_blobs)
    ref_centers, ref_sigs = _constellation_signatures(reference_blobs)
    if src_sigs is None or ref_sigs is None:
        return []

    ratio_test = cfg.get("ratio_test", _RATIO_TEST)
    matches = []
    for i, sig in enumerate(src_sigs):
        dists = np.linalg.norm(ref_sigs - sig, axis=1)
        order = np.argsort(dists)
        if len(order) < 2:
            continue
        best, second = dists[order[0]], dists[order[1]]
        if second <= 0 or best / second >= ratio_test:
            continue

        j = order[0]
        # blob centers are (row, col); Match expects (x, y) like ORB/LoFTR.
        source_xy = (float(src_centers[i, 1]), float(src_centers[i, 0]))
        reference_xy = (float(ref_centers[j, 1]), float(ref_centers[j, 0]))
        matches.append(Match(source_xy, reference_xy, confidence=1.0 - best / second))

    return matches
