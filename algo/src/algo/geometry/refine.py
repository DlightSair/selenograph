"""Stage 5.5 -- sub-pixel refinement and a guided second pass.

MAGSAC's own inlier selection already gets most of the achievable accuracy
at coarse-pyramid scale (CLAUDE.md's "known quality ceiling"), but two
things are still cheap wins once a first-pass transform exists:

  1. Refine each inlier's reference-side location to sub-pixel precision via
     local normalized cross-correlation around the matcher's own keypoint,
     instead of trusting a single (patch-quantized) pixel location.
  2. Use the refined transform as a geometric prior to search a small
     neighbourhood around points near each inlier -- pulling in near-miss
     correspondences the blind matchers missed. This is what actually helps
     on self-similar terrain: two identical-looking craters far apart are
     no longer confusable once the search is constrained to a small window
     around a geometrically-predicted location, instead of matching blind.

Operates on the crop-native source/reference arrays (not pyramid tiles),
since by the time pipeline.run reaches this stage, matches are already
expressed in that coordinate space -- but source_crop and reference_crop
are at very different native resolutions (the source/reference GSD ratio
pyramid/coarse_to_fine.py exists to bridge, here ~20x on the real Tycho
data). A first version of this module compared same-pixel-count windows
from each array directly -- e.g. a 25x25 *source*-native template (~50m
across) against a 37x37 *reference*-native search window (~1550m across)
-- which is not a valid NCC comparison at all (same bug pyramid-matching
exists to avoid, reintroduced here by skipping the pyramid for refinement).
Fixed by resampling the source-side template down to the reference's own
pixel size before correlating, so every NCC call compares like-for-like.

A second, separate bug the same first version had: `source_xy` is crop-
local (valid as an index into `source_crop` directly), but `reference_xy`
is *absolute* full-raster pixel coordinates (pipeline.run adds the window's
row/col offset back on, so preprocessing.relief can use it with the
reference raster's own affine transform) -- not a local index into
`reference_crop`. Indexing `reference_crop` with `reference_xy` directly
silently went out of bounds on every real inlier and made every refinement
attempt a no-op. Fixed by taking the crop's offset and subtracting it
before indexing, adding it back on every returned point.
"""

from __future__ import annotations

import cv2
import numpy as np
from skimage.transform import resize

from algo.matching.match import Match

_PATCH_HALF_REF = 3  # template half-size, in REFERENCE pixels (after resampling the source side down to it)
_SEARCH_HALF_REF = 6  # search-window half-size, in REFERENCE pixels
_DENSIFY_OFFSETS_REF = [(dx, dy) for dx in (-2, 0, 2) for dy in (-2, 0, 2) if (dx, dy) != (0, 0)]
_MIN_NCC = 0.5  # minimum normalized cross-correlation to accept a refined/densified point


def _extract(array: np.ndarray, cx: float, cy: float, half: int) -> np.ndarray | None:
    x0, y0 = int(round(cx)) - half, int(round(cy)) - half
    x1, y1 = x0 + 2 * half + 1, y0 + 2 * half + 1
    if x0 < 0 or y0 < 0 or y1 > array.shape[0] or x1 > array.shape[1]:
        return None
    return array[y0:y1, x0:x1]


def _source_template_at_reference_scale(source_crop: np.ndarray, sx: float, sy: float, gsd_ratio: float):
    """A (2*_PATCH_HALF_REF+1)-square template around (sx, sy) in source_crop,
    downsampled from a physically-equivalent, larger native-source patch so
    its pixel size matches the reference's GSD. `gsd_ratio` = reference GSD
    / source GSD, i.e. how many source pixels span one reference pixel."""
    half_src = max(int(round(_PATCH_HALF_REF * gsd_ratio)), _PATCH_HALF_REF)
    raw = _extract(source_crop, sx, sy, half_src)
    if raw is None:
        return None
    size = 2 * _PATCH_HALF_REF + 1
    return resize(raw.astype(np.float64), (size, size), anti_aliasing=True, preserve_range=True)


def _ncc_peak(template: np.ndarray, search: np.ndarray) -> tuple[float, float, float] | None:
    """Sub-pixel (x, y, score) of the best NCC match's top-left corner
    within `search`, via parabolic interpolation around the integer peak."""
    if template.shape[0] >= search.shape[0] or template.shape[1] >= search.shape[1]:
        return None

    result = cv2.matchTemplate(search.astype(np.float32), template.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    px, py = max_loc
    fx, fy = float(px), float(py)
    h, w = result.shape

    if 0 < px < w - 1:
        denom = result[py, px - 1] - 2 * result[py, px] + result[py, px + 1]
        if abs(denom) > 1e-9:
            fx += 0.5 * (result[py, px - 1] - result[py, px + 1]) / denom
    if 0 < py < h - 1:
        denom = result[py - 1, px] - 2 * result[py, px] + result[py + 1, px]
        if abs(denom) > 1e-9:
            fy += 0.5 * (result[py - 1, px] - result[py + 1, px]) / denom

    return fx, fy, float(max_val)


def _locate(template: np.ndarray, search: np.ndarray, search_x0: float, search_y0: float):
    peak = _ncc_peak(template, search)
    if peak is None or peak[2] < _MIN_NCC:
        return None
    px, py, score = peak
    return search_x0 + px + _PATCH_HALF_REF, search_y0 + py + _PATCH_HALF_REF, score


def refine_and_densify(
    inliers: list, source_crop: np.ndarray, reference_crop: np.ndarray, transform: np.ndarray,
    source_gsd: float, reference_gsd: float, reference_row_offset: int, reference_col_offset: int,
) -> list:
    """Sub-pixel-refines `inliers` and adds nearby densified matches found
    via guided template matching around the current transform's
    predictions. Never drops a point -- a failed refinement/densification
    attempt just keeps (or skips adding) the original.

    `reference_row_offset`/`reference_col_offset` convert between the
    absolute full-raster `reference_xy` matches carry and the local indices
    `reference_crop` needs -- see the module docstring's second bug note."""
    gsd_ratio = reference_gsd / source_gsd

    refined = []
    for m in inliers:
        sx, sy = m.source_xy
        rx, ry = m.reference_xy
        local_rx, local_ry = rx - reference_col_offset, ry - reference_row_offset

        template = _source_template_at_reference_scale(source_crop, sx, sy, gsd_ratio)
        search = _extract(reference_crop, local_rx, local_ry, _SEARCH_HALF_REF)
        if template is None or search is None:
            refined.append(m)
            continue

        located = _locate(template, search, round(local_rx) - _SEARCH_HALF_REF, round(local_ry) - _SEARCH_HALF_REF)
        if located is None:
            refined.append(m)
            continue

        new_local_rx, new_local_ry, score = located
        new_rxy = (new_local_rx + reference_col_offset, new_local_ry + reference_row_offset)
        refined.append(Match((sx, sy), new_rxy, max(m.confidence, score)))

    densified = []
    for m in refined:
        sx, sy = m.source_xy
        for dx_ref, dy_ref in _DENSIFY_OFFSETS_REF:
            cand_sx, cand_sy = sx + dx_ref * gsd_ratio, sy + dy_ref * gsd_ratio
            template = _source_template_at_reference_scale(source_crop, cand_sx, cand_sy, gsd_ratio)
            if template is None:
                continue

            predicted = cv2.perspectiveTransform(
                np.array([[[cand_sx, cand_sy]]], dtype=np.float32), transform
            )[0, 0]
            local_px, local_py = float(predicted[0]) - reference_col_offset, float(predicted[1]) - reference_row_offset
            search = _extract(reference_crop, local_px, local_py, _SEARCH_HALF_REF)
            if search is None:
                continue

            located = _locate(template, search, round(local_px) - _SEARCH_HALF_REF, round(local_py) - _SEARCH_HALF_REF)
            if located is None:
                continue

            new_local_rx, new_local_ry, score = located
            new_rxy = (new_local_rx + reference_col_offset, new_local_ry + reference_row_offset)
            densified.append(Match((cand_sx, cand_sy), new_rxy, score))

    return refined + densified
