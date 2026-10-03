"""geometry.parallax: DEM-driven displacement is recovered, with the right sign and size."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates

from algo.geometry.analysis import apply_homography
from algo.geometry.parallax import expected_view_tangents, fit_parallax


def test_recovers_parallax_coefficients_from_a_dem():
    rng = np.random.default_rng(0)
    H = np.array([[1.0, 0.0, 30.0], [0.0, 1.0, 20.0], [0, 0, 1.0]])  # source px -> reference px, axes aligned
    dem = gaussian_filter(rng.normal(size=(900, 900)), 25).astype(np.float32)
    dem = dem / dem.std() * 400.0  # ~400 m relief
    gsd = 5.0
    src = rng.uniform(100, 700, (900, 2))
    p = apply_homography(H, src)
    h = map_coordinates(dem, np.stack([p[:, 1], p[:, 0]]), order=1) - np.median(dem)
    tan_along, tan_cross = -0.40, 0.08  # along-track = source rows (y), cross-track = columns (x)
    ref = p + (h / gsd)[:, None] * np.array([[0.0, 1.0]]) * tan_along + (h / gsd)[:, None] * np.array([[1.0, 0.0]]) * tan_cross
    ref = ref + rng.normal(0, 0.1, ref.shape)

    fit = fit_parallax(src, ref, H, dem, gsd, centre_xy=(400, 400), expected=(0.4, 0.08))
    assert fit is not None
    assert abs(fit.alpha_along - tan_along) < 0.03, fit.info
    assert abs(fit.alpha_cross - tan_cross) < 0.03, fit.info
    assert fit.explained > 0.8


def test_flat_terrain_explains_nothing():
    rng = np.random.default_rng(1)
    H = np.eye(3)
    dem = np.zeros((500, 500), np.float32)
    dem += rng.normal(0, 0.01, dem.shape).astype(np.float32)
    src = rng.uniform(50, 450, (300, 2))
    ref = src + rng.normal(0, 0.2, src.shape)
    assert fit_parallax(src, ref, H, dem, 5.0, (250, 250)) is None


def test_expected_tangents_from_label_geometry():
    class M:
        camera, pitch, roll = "f", 0.5, 3.0

    along, cross = expected_view_tangents(M)
    assert abs(along - np.tan(np.radians(25.5))) < 1e-6 and abs(cross - np.tan(np.radians(3.0))) < 1e-6
