"""Applies a fitted transform to the source crop so it can be looked at next
to the reference, instead of only the sparse match-point overlay. The fitted
homography (`transform.json`, see `robust_fit.fit_transform`) maps
source_crop-native pixel coordinates to the reference RASTER's *absolute*
pixel coordinates -- that's what `preprocessing.relief` needs for its own
raster lookups. Visualizing the warp needs the opposite: a result indexable
into `reference_crop` directly, so the crop's row/col offset has to come
back off first (same offset subtraction `geometry.refine` and
`api.overlay`/`scripts.visualize_run` already do for the same reason).
"""

from __future__ import annotations

import cv2
import numpy as np


def warp_source_into_reference_frame(
    source_crop: np.ndarray,
    reference_crop: np.ndarray,
    transform: np.ndarray,
    reference_row_offset: float,
    reference_col_offset: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (warped_source, valid_mask): `warped_source` is `source_crop`
    resampled into `reference_crop`'s own shape/frame via `transform`, and
    `valid_mask` is True where that warp actually has source coverage (vs.
    the border fill for pixels the homography maps outside the source
    crop's extent) -- warped pixel *values* can legitimately be zero, so the
    mask is tracked explicitly rather than inferred from `warped_source == 0`.
    """
    offset = np.array(
        [[1.0, 0.0, -reference_col_offset], [0.0, 1.0, -reference_row_offset], [0.0, 0.0, 1.0]]
    )
    local_transform = offset @ np.asarray(transform, dtype=np.float64)
    height, width = reference_crop.shape[:2]

    warped_source = cv2.warpPerspective(
        source_crop.astype(np.float32), local_transform, (width, height), flags=cv2.INTER_LINEAR
    )
    valid_mask = cv2.warpPerspective(
        np.ones(source_crop.shape[:2], dtype=np.uint8),
        local_transform,
        (width, height),
        flags=cv2.INTER_NEAREST,
    ).astype(bool)

    return warped_source, valid_mask
