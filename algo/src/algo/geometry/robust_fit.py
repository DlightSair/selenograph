"""Stage 5 — outlier rejection and transform estimation, with sub-pixel refinement."""


def fit_transform(matches, geometry_cfg):
    """
    TODO:
    - Robustly fit `geometry_cfg['transform']` (homography/affine) with MAGSAC++
      (cv2.USAC_MAGSAC) or graph-cut RANSAC over `matches`.
    - For high-relief terrain (crater walls, where true 3D parallax between differing
      orbital viewpoints breaks a flat 2D homography), delegate to
      geometry.orthorectify.dtm_orthorectify instead.
    - After the initial fit, refine each inlier's location with local NCC/phase-correlation
      subpixel refinement to actually deliver sub-pixel accuracy.

    Returns (transform, inlier_matches).
    """
    raise NotImplementedError
