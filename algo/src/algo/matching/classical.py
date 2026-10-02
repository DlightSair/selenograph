"""Stage 3 (fallback) + Stage 4 — illumination-robust classical matcher and
uniform-distribution enforcement (grid-based adaptive non-max suppression).

Runs over the whole level tile (not per-keypoint patches around individual
low-confidence learned matches) -- simpler and more robust than trying to
crop tiny sub-patches, and still achieves the same "independent cross-check
on tiles the learned matcher struggled with" role.
"""

from __future__ import annotations

import cv2
import numpy as np

from algo.matching._tiling import downsample_for_matching
from algo.matching.learned import Match
from algo.preprocessing.illumination import normalize_illumination

_ORB_FEATURES = 4000
_LOWE_RATIO = 0.75
_MAX_TILE_PIXELS = 1_000_000  # see matching/_tiling.py's docstring -- tried raising to 3M on the
# real Tycho run and it was *worse* (6 inliers vs 16, and 2x slower): more native resolution
# surfaces more fine-scale repetitive crater texture, which is the self-similarity problem this
# whole project is fighting, not free detail. 1M was the better trade-off, not just the faster one.


def match_classical(level, matching_cfg) -> list[Match]:
    source_small, source_factor = downsample_for_matching(level.source_tile, _MAX_TILE_PIXELS)
    reference_small, reference_factor = downsample_for_matching(level.reference_tile, _MAX_TILE_PIXELS)

    source_struct, reference_struct = normalize_illumination(source_small, reference_small)
    source_8u = (source_struct * 255).astype(np.uint8)
    reference_8u = (reference_struct * 255).astype(np.uint8)

    orb = cv2.ORB_create(nfeatures=_ORB_FEATURES)
    kp_s, des_s = orb.detectAndCompute(source_8u, None)
    kp_r, des_r = orb.detectAndCompute(reference_8u, None)
    if des_s is None or des_r is None or len(kp_s) < 2 or len(kp_r) < 2:
        return []

    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = bf.knnMatch(des_s, des_r, k=2)

    matches = []
    for pair in raw_matches:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < _LOWE_RATIO * n.distance:
            confidence = 1.0 - (m.distance / 256.0)
            sx, sy = kp_s[m.queryIdx].pt
            rx, ry = kp_r[m.trainIdx].pt
            source_xy = (sx * source_factor, sy * source_factor)
            reference_xy = (rx * reference_factor, ry * reference_factor)
            matches.append(Match(source_xy, reference_xy, confidence))

    return matches


def enforce_uniform_distribution(matches: list[Match], anms_cfg: dict) -> list[Match]:
    """Caps `anms_cfg['max_matches_per_tile']` matches per grid_size x grid_size
    tile over the REFERENCE frame, so high-texture regions (crater rims)
    don't dominate over flat, low-texture regions (mare plains)."""
    if not matches:
        return matches

    xs = [m.reference_xy[0] for m in matches]
    ys = [m.reference_xy[1] for m in matches]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    grid_size = anms_cfg["grid_size"]
    cap = anms_cfg["max_matches_per_tile"]

    cell_w = (x_max - x_min) / grid_size or 1.0
    cell_h = (y_max - y_min) / grid_size or 1.0

    buckets: dict[tuple[int, int], list[Match]] = {}
    for m in matches:
        cx = min(int((m.reference_xy[0] - x_min) / cell_w), grid_size - 1)
        cy = min(int((m.reference_xy[1] - y_min) / cell_h), grid_size - 1)
        buckets.setdefault((cx, cy), []).append(m)

    kept = []
    for bucket in buckets.values():
        bucket.sort(key=lambda m: m.confidence, reverse=True)
        kept.extend(bucket[:cap])
    return kept
