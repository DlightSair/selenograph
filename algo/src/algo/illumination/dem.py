"""Bring a DEM onto the reference crop's pixel grid and render it under a given Sun.

The DEM can live in any CRS (LOLA polar DEMs are polar stereographic, the TMC-2 DTM is
geographic, references are local equirectangular or polar stereographic); it is resampled
with `rasterio.warp.reproject` onto the reference raster's own grid, over the crop plus a
margin. The margin matters at low Sun: a 1 km ridge casts a 30 km shadow at 2 degrees, and
a shadow can only fall on the crop if the ridge casting it is in the DEM window.

Sun azimuth is defined against local north, but a map-projected raster is only
"north-up" on a cylindrical grid. On a polar-stereographic grid north is rotated by the
meridian convergence, so the azimuth handed to the renderer must be rotated by it.
"""

from __future__ import annotations

import math

import numpy as np
import pyproj
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from algo.illumination.relight import render_dem
from algo.utils.io import MOON_RADIUS_M, pixel_size_m


def dem_on_reference_grid(
    dem_path: str,
    reference_transform: Affine,
    reference_crs,
    window: tuple[int, int, int, int],
    margin_px: int = 0,
) -> np.ndarray:
    """DEM heights (float32, NaN where the DEM has no data) on the reference pixel grid over
    `window` = (row_start, row_stop, col_start, col_stop) grown by `margin_px` on every side."""
    r0, r1, c0, c1 = window
    r0m, c0m = r0 - margin_px, c0 - margin_px
    h, w = (r1 - r0) + 2 * margin_px, (c1 - c0) + 2 * margin_px
    dst_transform = reference_transform * Affine.translation(c0m, r0m)
    out = np.full((h, w), np.nan, np.float32)
    with rasterio.open(dem_path) as ds:
        nodata = ds.nodata
        # scale/offset tags (LOLA ADJ COGs store int16 + scale) are applied by GDAL when present
        scale = ds.scales[0] if ds.scales and ds.scales[0] not in (None, 0) else 1.0
        offset = ds.offsets[0] if ds.offsets and ds.offsets[0] is not None else 0.0
        reproject(
            rasterio.band(ds, 1), out, src_transform=ds.transform, src_crs=ds.crs,
            dst_transform=dst_transform, dst_crs=reference_crs, resampling=Resampling.bilinear,
            src_nodata=nodata, dst_nodata=np.nan,
        )
    out = out * scale + offset
    if nodata is not None:
        out[np.isclose(out, nodata * scale + offset)] = np.nan
    return out


def grid_north_offset_deg(reference_crs, transform: Affine, row: float, col: float) -> float:
    """Angle (degrees, clockwise) from the raster's "up" to local north at pixel (row, col).
    0 for cylindrical grids; nonzero on polar stereographic grids."""
    x, y = transform * (col + 0.5, row + 0.5)
    to_lonlat = pyproj.Transformer.from_crs(reference_crs, pyproj.CRS.from_proj4(
        f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs"), always_xy=True)
    lon, lat = to_lonlat.transform(x, y)
    # a point 1 km along local north, projected back to the grid, tells us where "north" points
    d = 1000.0 / MOON_RADIUS_M
    lat2 = lat + math.degrees(d)
    if abs(lat2) > 90:
        lat2 = lat - math.degrees(d)
        sign = -1.0
    else:
        sign = 1.0
    to_grid = pyproj.Transformer.from_crs(to_lonlat.target_crs, reference_crs, always_xy=True)
    x2, y2 = to_grid.transform(lon, lat2)
    dx, dy = (x2 - x) * sign, (y2 - y) * sign
    # grid y points up the image for north-up rasters (row index decreases with y)
    return math.degrees(math.atan2(dx, dy))


def relit_reference(
    dem_path: str,
    reference_transform: Affine,
    reference_crs,
    window: tuple[int, int, int, int],
    sun_azimuth: float,
    sun_elevation: float,
    margin_px: int | None = None,
    **render_kwargs,
) -> np.ndarray | None:
    """The DEM as lit by the given Sun, on the reference crop grid (uint8-range float32, 0 where the
    DEM has no coverage). Returns None if the DEM does not cover the window."""
    px, _ = pixel_size_m(reference_transform, reference_crs)
    if margin_px is None:
        # shadows from outside the crop: relief ~ 1 km at this Sun, capped at 15 km of reach
        reach_m = min(15_000.0, 1000.0 / max(math.tan(math.radians(max(sun_elevation, 0.5))), 1e-3))
        margin_px = int(reach_m / px)
    r0, r1, c0, c1 = window
    dem = dem_on_reference_grid(dem_path, reference_transform, reference_crs, window, margin_px)
    inner = dem[margin_px:dem.shape[0] - margin_px, margin_px:dem.shape[1] - margin_px]
    if not np.isfinite(inner).any() or np.isfinite(inner).mean() < 0.3:
        return None
    # azimuth is against local north; north points `conv` degrees clockwise from the grid's "up" on polar
    # grids, so a compass azimuth is that much further clockwise relative to image-up
    conv = grid_north_offset_deg(reference_crs, reference_transform, (r0 + r1) / 2, (c0 + c1) / 2)
    img = render_dem(dem, px, (sun_azimuth + conv) % 360.0, sun_elevation, **render_kwargs)
    img = img[margin_px:img.shape[0] - margin_px, margin_px:img.shape[1] - margin_px]
    lo, hi = np.percentile(img[np.isfinite(inner)], [0.5, 99.5])
    img = np.clip((img - lo) / max(hi - lo, 1e-6) * 254.0 + 1.0, 1.0, 255.0)
    img[~np.isfinite(inner)] = 0.0
    return img.astype(np.float32)
