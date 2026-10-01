"""Stage 3 (primary) — pretrained dense matcher (e.g. LoFTR via kornia.feature.LoFTR).

No lunar-specific training needed to start: use off-the-shelf pretrained weights and
only fine-tune later if time allows and a weakly-labeled correspondence set exists
(e.g. bootstrapped from the classical matcher's high-confidence inliers).
"""


class Match:
    def __init__(self, source_xy, reference_xy, confidence):
        self.source_xy = source_xy
        self.reference_xy = reference_xy
        self.confidence = confidence


def match_learned(level, matching_cfg) -> list[Match]:
    """
    TODO:
    - Run kornia.feature.LoFTR (or similar detector-free transformer matcher) on
      `level.source_tile` vs `level.reference_tile`.
    - Return a list of Match objects with confidence scores so the pipeline can route
      low-confidence tiles to the classical fallback (Stage 3 cross-check).
    """
    raise NotImplementedError
