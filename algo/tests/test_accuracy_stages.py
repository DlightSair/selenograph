"""Tests for the accuracy-improvement stages added on top of the first real
end-to-end run (see CLAUDE.md's "accuracy improvements" section): crater-
constellation signatures, geometric-consistency confidence boosting, DTM
relief weighting, and sub-pixel NCC peak-finding. Synthetic data only -- the
real-data path is covered end-to-end by test_pipeline.py's slow test."""

from __future__ import annotations

import numpy as np
import pytest

from algo.matching.learned import Match


def test_crater_constellation_signature_is_scale_rotation_invariant():
    from algo.matching.crater import _constellation_signatures

    rng = np.random.default_rng(0)
    points = rng.uniform(0, 100, size=(8, 2))
    _, sig_a = _constellation_signatures(points)

    theta = np.radians(37)
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    transformed = (points @ rot.T) * 2.5  # rotate 37 degrees, scale up 2.5x
    _, sig_b = _constellation_signatures(transformed)

    assert sig_a is not None and sig_b is not None
    np.testing.assert_allclose(sig_a, sig_b, atol=1e-6)


def test_crater_constellation_signature_needs_enough_blobs():
    from algo.matching.crater import _NUM_NEIGHBORS, _constellation_signatures

    too_few = np.zeros((_NUM_NEIGHBORS, 2))
    centers, sigs = _constellation_signatures(too_few)
    assert centers is None and sigs is None


def test_boost_by_global_consistency_prefers_mutually_consistent_matches():
    from algo.geometry.consistency import boost_by_global_consistency

    rng = np.random.default_rng(1)
    base = rng.uniform(0, 200, size=(5, 2))
    translation = np.array([50.0, -30.0])
    matches = [Match(tuple(p), tuple(p + translation), confidence=0.5) for p in base]
    # Two matches with an unrelated, inconsistent implied scale/rotation.
    matches.append(Match((10.0, 10.0), (999.0, 5.0), confidence=0.5))
    matches.append(Match((20.0, 180.0), (3.0, 777.0), confidence=0.5))

    boosted = boost_by_global_consistency(matches)

    consistent_conf = [m.confidence for m in boosted[:5]]
    noise_conf = [m.confidence for m in boosted[5:]]
    assert min(consistent_conf) > max(noise_conf)
    assert all(c >= 0.5 for c in noise_conf)  # never penalized, only ever boosted


def test_boost_by_global_consistency_is_a_noop_below_four_matches():
    from algo.geometry.consistency import boost_by_global_consistency

    matches = [Match((0.0, 0.0), (1.0, 1.0), confidence=0.5)] * 3
    result = boost_by_global_consistency(matches)
    assert all(m.confidence == 0.5 for m in result)


def test_relief_weighting_down_weights_steep_slope_matches(tmp_path):
    import pyproj
    import rasterio
    from rasterio.transform import from_origin

    from algo.preprocessing.relief import apply_relief_risk_weighting
    from algo.utils.io import MOON_RADIUS_M

    moon_crs = pyproj.CRS.from_proj4(f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")

    size = 40
    elevation = np.zeros((size, size), dtype=np.int16)
    for col in range(size):
        elevation[:, col] = (size // 2 - col) * 500 if col < size // 2 else 0  # steep ramp | flat

    transform = from_origin(348.0, -42.0, 0.001, 0.001)
    dem_path = tmp_path / "dem.tif"
    with rasterio.open(
        dem_path, "w", driver="GTiff", height=size, width=size, count=1, dtype="int16",
        crs=moon_crs.to_wkt(), transform=transform,
    ) as ds:
        ds.write(elevation, 1)

    steep_match = Match((0.0, 0.0), (5.0, 20.0), confidence=1.0)  # left half: steep ramp
    flat_match = Match((0.0, 0.0), (35.0, 20.0), confidence=1.0)  # right half: flat

    result = apply_relief_risk_weighting([steep_match, flat_match], transform, moon_crs, str(dem_path))

    assert result[0].confidence < result[1].confidence
    assert result[1].confidence == pytest.approx(1.0, abs=1e-6)


def test_relief_weighting_leaves_out_of_coverage_matches_unchanged(tmp_path):
    import pyproj
    import rasterio
    from rasterio.transform import from_origin

    from algo.preprocessing.relief import apply_relief_risk_weighting
    from algo.utils.io import MOON_RADIUS_M

    moon_crs = pyproj.CRS.from_proj4(f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")
    transform = from_origin(348.0, -42.0, 0.001, 0.001)
    dem_path = tmp_path / "dem.tif"
    with rasterio.open(
        dem_path, "w", driver="GTiff", height=10, width=10, count=1, dtype="int16",
        crs=moon_crs.to_wkt(), transform=transform,
    ) as ds:
        ds.write(np.zeros((10, 10), dtype=np.int16), 1)

    far_away = Match((0.0, 0.0), (10_000.0, 10_000.0), confidence=0.7)
    result = apply_relief_risk_weighting([far_away], transform, moon_crs, str(dem_path))
    assert result[0].confidence == pytest.approx(0.7)


def test_ncc_peak_finds_known_offset():
    import cv2

    from algo.geometry.refine import _ncc_peak

    rng = np.random.default_rng(2)
    base = rng.uniform(0, 1, size=(60, 60)).astype(np.float32)
    base = cv2.GaussianBlur(base, (0, 0), sigmaX=2.0)

    template = base[20:31, 20:31]
    search = base[10:50, 10:50]  # same content, template's top-left sits at (10, 10) within search

    peak = _ncc_peak(template, search)
    assert peak is not None
    fx, fy, score = peak
    assert abs(fx - 10) < 1.0
    assert abs(fy - 10) < 1.0
    assert score > 0.9
