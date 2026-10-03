"""Tests for preprocessing/grid.py's reference-window projection, in
particular the longitude-wraparound handling: pyproj normalizes longitude to (-180, 180] before applying a
target CRS's projection formula, but the LROC NAC ROI mosaic's
Equirectangular CRS was built from unwrapped (always 0-360) longitude, so
the two conventions land a full lunar circumference apart. Synthetic CRS
here, not the real downloaded mosaic -- keeps this test fast and independent
of local data."""

from __future__ import annotations

import math

import pyproj
import pytest

from algo.preprocessing.grid import _MOON_GEOGRAPHIC, _project_wrap_safe
from algo.utils.io import MOON_RADIUS_M


def _unwrapped_eqc_xy(lon_deg: float, lat_deg: float, lat_ts_deg: float) -> tuple[float, float]:
    """The textbook Equirectangular forward formula, applied directly to the
    given longitude with no wraparound -- this is what a PDS/ISIS-style
    "unwrapped 0-360" product's pixel grid actually encodes, and what
    _project_wrap_safe must recover."""
    x = MOON_RADIUS_M * math.radians(lon_deg) * math.cos(math.radians(lat_ts_deg))
    y = MOON_RADIUS_M * math.radians(lat_deg)
    return x, y


def test_project_wrap_safe_recovers_unwrapped_equirectangular_coordinates():
    lat_ts = -43.0
    eqc_crs = pyproj.CRS.from_proj4(f"+proj=eqc +lat_ts={lat_ts} +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R={MOON_RADIUS_M} +units=m")
    transformer = pyproj.Transformer.from_crs(_MOON_GEOGRAPHIC, eqc_crs, always_xy=True)

    lon, lat = 349.3, -43.88  # a longitude far enough from 0 for the wrap bug to be obvious
    expected_x, expected_y = _unwrapped_eqc_xy(lon, lat, lat_ts)

    # Anchor close to the correct (unwrapped) answer -- as pipeline.run does, using the
    # reference raster's own upper-left corner, which necessarily sits in the unwrapped branch.
    x, y = _project_wrap_safe(transformer, eqc_crs, lon, lat, anchor_x=expected_x, anchor_y=expected_y)

    assert x == pytest.approx(expected_x, abs=1.0)
    assert y == pytest.approx(expected_y, abs=1.0)


def test_project_wrap_safe_falls_back_to_proj_for_non_equirectangular_crs():
    # An orthographic CRS (like the original QuickMap WAC reference) has no unwrapped-longitude
    # quirk -- _project_wrap_safe should just return pyproj's own (correct) answer unchanged.
    ortho_crs = pyproj.CRS.from_proj4(f"+proj=ortho +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +lat_0=0 +lon_0=0 +units=m")
    transformer = pyproj.Transformer.from_crs(_MOON_GEOGRAPHIC, ortho_crs, always_xy=True)

    lon, lat = 10.0, -5.0
    expected_x, expected_y = transformer.transform(lon, lat)

    x, y = _project_wrap_safe(transformer, ortho_crs, lon, lat, anchor_x=0.0, anchor_y=0.0)
    assert (x, y) == pytest.approx((expected_x, expected_y))
