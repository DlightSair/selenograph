"""Stage 3 (primary) -- pretrained dense matcher: LoFTR ('outdoor' weights) run with ONNX Runtime
(matching/loftr_onnx.py), so neither torch nor kornia is needed at run time. No lunar-specific
training: a transformer trained on terrestrial stereo pairs still picks up generic texture/structure
correspondence. Runs on the plain contrast-stretched tile (not the Gabor structure map used by the
classical fallback) -- relies on the pretrained model's own robustness rather than a hand-built
illumination-invariant representation.

The ONNX graphs (models/loftr_*.onnx, gitignored) are produced once from the official checkpoint by
scripts/export_loftr_onnx.py, which is the only place torch/kornia are used.

Falls back to matching.classical when confidence is low (shadowed crater interiors, featureless mare),
when onnxruntime is missing, or when the model files haven't been built.
"""

from __future__ import annotations

import numpy as np

from algo.matching import loftr_onnx

_MAX_TILE_PIXELS = 1_000_000  # ~1000x1000; see match_learned's size-guard comment


class Match:
    def __init__(self, source_xy, reference_xy, confidence):
        self.source_xy = source_xy
        self.reference_xy = reference_xy
        self.confidence = confidence


def _normalise(image: np.ndarray) -> np.ndarray:
    """Grayscale float array -> float32 in [0, 1], H/W rounded down to a multiple of 8 (LoFTR's
    internal downsampling requirement)."""
    h, w = image.shape
    cropped = image[: (h // 8) * 8, : (w // 8) * 8].astype(np.float32)
    span = cropped.max() - cropped.min()
    return (cropped - cropped.min()) / (span if span > 0 else 1.0)


def match_learned(level, matching_cfg) -> list[Match]:
    if not loftr_onnx.available():
        raise NotImplementedError("LoFTR ONNX models or onnxruntime not available -- run scripts/export_loftr_onnx.py")
    if min(level.source_tile.shape) < 8 or min(level.reference_tile.shape) < 8:
        return []
    source_pixels = level.source_tile.shape[0] * level.source_tile.shape[1]
    reference_pixels = level.reference_tile.shape[0] * level.reference_tile.shape[1]
    if source_pixels > _MAX_TILE_PIXELS or reference_pixels > _MAX_TILE_PIXELS:
        # LoFTR's transformer attention is quadratic in (H/8 * W/8); a near-native-resolution
        # pyramid level (possible once source/reference GSD are close, unlike the ~20x WAC-era
        # gap this was originally tuned against) can be tens of millions of pixels and exhausts
        # CPU memory in the CNN backbone alone -- fall back to classical/crater matching instead
        # of crashing. Verified on the real Tycho run with the 5m/px NAC reference.
        raise NotImplementedError(
            f"tile too large for LoFTR ({level.source_tile.shape} / {level.reference_tile.shape})"
        )

    k0, k1, conf = loftr_onnx.match(_normalise(level.source_tile), _normalise(level.reference_tile))
    return [Match(tuple(k0[i]), tuple(k1[i]), float(conf[i])) for i in range(len(conf))]
