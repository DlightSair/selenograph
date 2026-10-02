"""Stage 4.5b -- DTM-based relief-risk weighting.

Full photogrammetric orthorectification (geometry/orthorectify.py) needs a
rigorous sensor pointing model we don't have for Calibrated products -- only
a coarse, uncorrected ground-control grid (preprocessing/grid.py). But a
real DEM is on disk, and it is useful far more cheaply than that: local
terrain ruggedness (slope) is a reasonable proxy for relief-induced parallax
risk between the two orbiters' differing viewing geometries, and is also
exactly the kind of terrain (crater walls/terraces) most likely to produce
the repeated small-scale structure that confuses area-based matching in the
first place -- so it doubles as a risk signal for both failure modes without
needing either sensor's exact pointing.

Soft weighting rather than a hard filter: we only have ~30-50 candidate
matches to begin with (CLAUDE.md's "known quality ceiling"), so an outright
drop risks discarding the only match available in a given area. Confidence
is scaled down on steep terrain instead, so matching.classical.
enforce_uniform_distribution's per-cell ranking prefers flatter-terrain
matches without destroying the candidate pool.
"""

from __future__ import annotations

import numpy as np
import pyproj
import rasterio
from rasterio.transform import rowcol
from rasterio.windows import Window

from algo.utils.io import MOON_RADIUS_M, pixel_size_m

_MOON_GEOGRAPHIC = pyproj.CRS.from_proj4(f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")
_SAMPLE_HALF_WINDOW = 3  # DEM pixels either side, for a central-difference slope estimate
_MAX_SLOPE_DEG = 89.0


def _slope_deg_at(dem, dem_transform, dx_m: float, dy_m: float, row: int, col: int) -> float:
    half = _SAMPLE_HALF_WINDOW
    row_start, col_start = row - half, col - half
    if row_start < 0 or col_start < 0 or row + half >= dem.height or col + half >= dem.width:
        return float("nan")

    window = Window(col_start, row_start, 2 * half + 1, 2 * half + 1)
    patch = dem.read(1, window=window).astype(np.float64)
    nodata = dem.nodata
    if nodata is not None and (patch == nodata).any():
        return float("nan")

    dzdy, dzdx = np.gradient(patch)
    dzdx_m = dzdx[half, half] / dx_m
    dzdy_m = dzdy[half, half] / dy_m
    return float(np.degrees(np.arctan(np.hypot(dzdx_m, dzdy_m))))


def apply_relief_risk_weighting(matches: list, reference_transform, reference_crs, dem_path: str) -> list:
    """Scales each match's confidence by cos(slope) at its reference-side
    ground location, sampled from the DEM. Matches outside the DEM's
    coverage, or where the DEM has nodata, are left unchanged -- unknown
    risk is not treated as high risk."""
    if not matches:
        return matches

    to_moon = pyproj.Transformer.from_crs(reference_crs, _MOON_GEOGRAPHIC, always_xy=True)

    with rasterio.open(dem_path) as dem:
        dem_transform = dem.transform
        dx_m, dy_m = pixel_size_m(dem_transform, dem.crs)

        for m in matches:
            x, y = reference_transform @ m.reference_xy
            lon, lat = to_moon.transform(x, y)
            # pyproj's geographic output is conventionally (-180, 180], but every longitude
            # elsewhere in this codebase (AOI config, the ground-control grid, this DEM's own
            # bounds) is 0-360 -- normalizing here is what makes DEM coverage actually match
            # (verified on real data: without this, every lookup missed the DEM entirely and
            # relief weighting was silently a no-op).
            lon = lon % 360
            row, col = rowcol(dem_transform, lon, lat)
            row, col = int(row), int(col)

            slope = _slope_deg_at(dem, dem_transform, dx_m, dy_m, row, col)
            if np.isnan(slope):
                continue

            # cos(slope) as the penalty: flat ground keeps full confidence, steep crater
            # walls are down-weighted smoothly, floored so a noisy slope estimate never
            # becomes a hard veto (a match is never killed outright by relief alone).
            capped = min(slope, _MAX_SLOPE_DEG)
            weight = max(float(np.cos(np.radians(capped))), 0.05)
            m.confidence *= weight

    return matches
