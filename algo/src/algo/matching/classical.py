"""Stage 3 (fallback) + Stage 4 — illumination-robust classical matcher and uniform-
distribution enforcement (grid-based adaptive non-max suppression).
"""

from algo.matching.learned import Match


def match_classical(level, low_confidence_matches, matching_cfg) -> list[Match]:
    """
    TODO:
    - Detect phase-congruency / RIFT-style features (log-Gabor filter bank response)
      on `level.source_tile` / `level.reference_tile` — robust to nonlinear radiometric
      shifts that raw-gradient detectors (SIFT/ORB) aren't.
    - Used as a cross-check specifically on tiles where the learned matcher (Stage 3
      primary) returned low-confidence or too few matches (e.g. deep-shadow regions
      near crater rims, where a matcher pretrained on Earth imagery may not generalize).
    """
    raise NotImplementedError


def enforce_uniform_distribution(matches: list[Match], anms_cfg) -> list[Match]:
    """
    Stage 4 — grid-based adaptive non-max suppression: cap `anms_cfg['max_matches_per_tile']`
    matches per `anms_cfg['grid_size']` x grid_size tile so high-texture regions (crater
    rims) don't dominate over flat, low-texture regions (mare plains). Directly implements
    the "maintaining uniform distribution across the images" requirement.
    """
    raise NotImplementedError
