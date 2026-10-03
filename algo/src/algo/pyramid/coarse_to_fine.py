"""Stage 2 — build matchable (source_tile, reference_tile) pairs across the
~20x GSD gap between a Calibrated TMC-2/OHRC crop and the LRO reference tile.

ORB/SIFT-style descriptors aren't scale-invariant across an order of
magnitude, so we can't just match full-res source against the reference
directly. Instead, for each source pyramid level we resample the reference
to that level's effective metres/pixel (using the GSD values from Stage 0),
so every level is matched at a shared physical scale. Levels that would need
an unreasonably large reference resize (e.g. upsampling the small reference
~20x to match native source resolution) are skipped -- that's the job of
later refinement against the coarse transform, not raw re-matching.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.transform import rescale

MAX_REFERENCE_RESIZE = 5.0  # skip pyramid levels needing a more extreme reference resample -- see
# CLAUDE.md's second-AOI section: at 4.0 this was a near-miss cutoff (a second-AOI level whose
# true ratio was 4.72x got skipped over a source GSD difference of under 1 m/px), collapsing a
# whole AOI to a single near-native-resolution level with no coarse anchor. 5.0 still excludes the
# genuinely unreasonable resizes (e.g. 19x) this guard exists for.


@dataclass
class Level:
    source_tile: np.ndarray
    reference_tile: np.ndarray
    source_scale: float  # multiply a level-space source coord by this to get crop-native coords
    reference_scale: float  # multiply a level-space reference coord by this to get reference-native coords
    level_gsd: float  # metres/pixel shared by both tiles at this level


def align_coarse_to_fine(
    source: np.ndarray, reference: np.ndarray, source_gsd: float, reference_gsd: float, pyramid_cfg: dict
) -> list[Level]:
    levels = []
    for i in range(pyramid_cfg["levels"]):
        source_scale = pyramid_cfg["downsample_factor"] ** i
        level_gsd = source_gsd * source_scale
        reference_scale = reference_gsd / level_gsd

        if not (1 / MAX_REFERENCE_RESIZE <= reference_scale <= MAX_REFERENCE_RESIZE):
            continue

        source_tile = rescale(source, 1 / source_scale, anti_aliasing=True, preserve_range=True)
        reference_tile = rescale(reference, reference_scale, anti_aliasing=True, preserve_range=True)
        levels.append(Level(source_tile, reference_tile, source_scale, 1 / reference_scale, level_gsd))

    return levels
