"""Stage 3 (primary) — pretrained dense matcher: kornia's LoFTR ('outdoor'
weights). No lunar-specific training: a transformer trained on terrestrial
stereo pairs still picks up generic texture/structure correspondence. Runs
on the plain contrast-stretched tile (not the Gabor structure map used by
the classical fallback) -- relies on the pretrained model's own robustness
rather than a hand-built illumination-invariant representation.

kornia's LoFTR(pretrained="outdoor") hardcodes a dead academic HTTP host
(cmp.felk.cvut.cz) for the checkpoint download. We load the same checkpoint
(verified identical, from the official kornia HuggingFace org) from
algo/models/loftr_outdoor.ckpt instead, downloaded once via
scripts/download_loftr_weights.py.

Falls back to matching.classical when confidence is low (shadowed crater
interiors, featureless mare), when torch/kornia aren't installed, or when
the checkpoint hasn't been downloaded.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import kornia.feature as KF
    import torch

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

_CHECKPOINT_PATH = Path(__file__).parents[3] / "models" / "loftr_outdoor.ckpt"
_MAX_TILE_PIXELS = 1_000_000  # ~1000x1000; see match_learned's size-guard comment

_matcher = None
_load_failed = False


class Match:
    def __init__(self, source_xy, reference_xy, confidence):
        self.source_xy = source_xy
        self.reference_xy = reference_xy
        self.confidence = confidence


def _get_matcher():
    global _matcher, _load_failed
    if _load_failed:
        raise NotImplementedError("LoFTR checkpoint unavailable")
    if _matcher is None:
        if not _CHECKPOINT_PATH.exists():
            _load_failed = True
            raise NotImplementedError(
                f"LoFTR checkpoint not found at {_CHECKPOINT_PATH} -- run scripts/download_loftr_weights.py"
            )
        try:
            matcher = KF.LoFTR(pretrained=None)
            checkpoint = torch.load(_CHECKPOINT_PATH, map_location=torch.device("cpu"))
            matcher.load_state_dict(checkpoint["state_dict"])
            matcher.eval()
            _matcher = matcher
        except Exception as e:
            _load_failed = True
            raise NotImplementedError(f"LoFTR checkpoint failed to load: {e}") from e
    return _matcher


def _to_tensor(image: np.ndarray):
    """Grayscale float array -> 1x1xHxW tensor in [0, 1], H/W rounded down to
    a multiple of 8 (LoFTR's internal downsampling requirement)."""
    h, w = image.shape
    h8, w8 = (h // 8) * 8, (w // 8) * 8
    cropped = image[:h8, :w8].astype(np.float32)
    span = cropped.max() - cropped.min()
    norm = (cropped - cropped.min()) / (span if span > 0 else 1.0)
    return torch.from_numpy(norm)[None, None]


def match_learned(level, matching_cfg) -> list[Match]:
    if not _AVAILABLE:
        raise NotImplementedError("torch/kornia not installed")
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

    matcher = _get_matcher()
    source_t = _to_tensor(level.source_tile)
    reference_t = _to_tensor(level.reference_tile)

    with torch.no_grad():
        out = matcher({"image0": source_t, "image1": reference_t})

    kpts0 = out["keypoints0"].numpy()
    kpts1 = out["keypoints1"].numpy()
    conf = out["confidence"].numpy()

    return [Match(tuple(kpts0[i]), tuple(kpts1[i]), float(conf[i])) for i in range(len(conf))]
