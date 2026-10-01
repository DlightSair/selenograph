"""Stage 5 — outlier rejection and transform estimation.

Full DTM-based orthorectification (geometry.orthorectify) for high-relief
terrain is deferred -- homography is the only transform implemented so far.
Sub-pixel refinement of inliers (local NCC/phase-correlation around each
match) is also deferred; MAGSAC++'s own inlier selection already accounts
for most of the achievable accuracy gain at this stage.
"""

from __future__ import annotations

import cv2
import numpy as np

_RANSAC_METHODS = {"magsac": cv2.USAC_MAGSAC, "ransac": cv2.RANSAC}


def fit_transform(matches: list, geometry_cfg: dict) -> tuple[np.ndarray | None, list]:
    if len(matches) < 4:
        return None, []

    src_pts = np.array([m.source_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)
    dst_pts = np.array([m.reference_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)

    method = _RANSAC_METHODS[geometry_cfg["ransac"]]
    transform, mask = cv2.findHomography(
        src_pts, dst_pts, method=method, ransacReprojThreshold=geometry_cfg["reproj_threshold_px"]
    )

    if transform is None:
        return None, []

    inlier_mask = mask.ravel().astype(bool)
    inliers = [m for m, keep in zip(matches, inlier_mask) if keep]
    return transform, inliers
