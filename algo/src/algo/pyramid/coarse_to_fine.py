"""Stage 2 — coarse-to-fine scale alignment; handles up to ~150-300x GSD gaps."""


def align_coarse_to_fine(source_normalized, reference_normalized, pyramid_cfg):
    """
    TODO:
    - Downsample both images to a common coarse GSD (e.g. reference's native WAC scale)
      and get an initial affine/homography estimate there.
    - Walk up `pyramid_cfg['levels']` resolution levels (each `downsample_factor` finer),
      re-matching tiles projected via the previous level's transform, until matching
      native-resolution source patches against native-resolution reference patches.

    Returns a list of per-level (source_tile, reference_tile, running_transform) tuples
    for Stage 3 to consume.
    """
    raise NotImplementedError
