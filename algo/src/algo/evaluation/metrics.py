"""Stage 6 — evaluation metrics: RMSE, inlier count/ratio, spatial uniformity."""


def evaluate(matches, inliers, transform, evaluation_cfg) -> dict:
    """
    TODO:
    - RMSE of inlier residuals after applying `transform`.
    - inlier_count = len(inliers); inlier_ratio = len(inliers) / len(matches).
    - Spatial-uniformity metric: coefficient of variation of inlier match density across
      a grid over the image (low CoV == matches spread evenly, satisfying the "uniform
      distribution across the images" requirement).
    - Write registered output + match-point table to `evaluation_cfg['output_dir']`.

    Returns a dict of {rmse, inlier_count, inlier_ratio, uniformity_cov}.
    """
    raise NotImplementedError
