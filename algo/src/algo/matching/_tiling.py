"""Shared helper for the classical and crater matchers: both run dense
per-pixel operations (Gabor filtering + CLAHE, blob detection) whose cost
scales with tile area. A near-native-resolution pyramid level is now
reachable (CLAUDE.md's "Reference data swap" -- source/reference GSD went
from a ~20x gap, where the coarse-to-fine pyramid's `MAX_REFERENCE_RESIZE`
cap always kept levels small, to ~1.2x, where the finest level can be tens
of millions of pixels). Verified on the real Tycho run: without a cap here,
a single level's classical matching alone took long enough to blow through a
30-minute background-task limit (LoFTR got an equivalent guard already,
matching/learned.py's `_MAX_TILE_PIXELS`, since it crashed outright rather
than just being slow).
"""

from __future__ import annotations

import math

import numpy as np
from skimage.transform import resize


def downsample_for_matching(tile: np.ndarray, max_pixels: int) -> tuple[np.ndarray, float]:
    """Returns (possibly-downsampled tile, factor) where factor is what to
    multiply an (x, y) coordinate found in the returned tile by to get back
    to `tile`'s own native pixel space. factor is 1.0 (no-op) when `tile`
    is already within budget."""
    height, width = tile.shape
    if height * width <= max_pixels:
        return tile, 1.0

    factor = math.sqrt((height * width) / max_pixels)
    new_height, new_width = max(int(height / factor), 1), max(int(width / factor), 1)
    small = resize(tile.astype(np.float64), (new_height, new_width), anti_aliasing=True, preserve_range=True)
    return small, factor
