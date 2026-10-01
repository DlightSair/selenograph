"""Stage 1 — illumination-invariant structure representation, used by the
classical matcher (matching.classical).

A full DEM-based hillshade re-rendering (matching each image's own sun
geometry) isn't viable with the data we actually have: the LRO reference is
a pre-blended QuickMap mosaic with no single sun angle to target, not raw
calibrated radiance. So we use the documented fallback instead -- a
multi-orientation Gabor-energy "structure map" that responds to edges and
texture roughly independently of absolute brightness, which is what
actually differs between a grazing-light TMC-2 strip and the reference's
own baked-in lighting. The learned matcher (matching.learned) does NOT use
this -- it runs on the plain contrast-stretched tile, relying on whatever
illumination robustness its pretrained weights already have.
"""

from __future__ import annotations

import numpy as np
from skimage.exposure import equalize_adapthist
from skimage.filters import gabor

_ORIENTATIONS = np.linspace(0, np.pi, 6, endpoint=False)
_FREQUENCIES = (0.1, 0.25)


def _gabor_energy(image: np.ndarray) -> np.ndarray:
    norm = image.astype(np.float64)
    span = norm.max() - norm.min()
    norm = (norm - norm.min()) / (span if span > 0 else 1.0)
    contrast = equalize_adapthist(norm, clip_limit=0.02)

    energy = np.zeros_like(contrast)
    for theta in _ORIENTATIONS:
        for freq in _FREQUENCIES:
            real, imag = gabor(contrast, frequency=freq, theta=theta)
            energy = np.maximum(energy, np.hypot(real, imag))

    peak = energy.max()
    return energy / (peak if peak > 0 else 1.0)


def normalize_illumination(source: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns (source_structure, reference_structure), both float64 in [0, 1]."""
    return _gabor_energy(source), _gabor_energy(reference)
