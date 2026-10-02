"""Ground-control grid for Chandrayaan-2 Calibrated products.

Calibrated OHRC/TMC-2 products are NOT map-projected (that's the whole
problem this pipeline solves), so they can't be cropped by lat/lon the way a
georeferenced raster can. Each product ships a geometry/*_g_grd_*.csv grid
alongside it -- (Longitude, Latitude, Pixel, Scan) control points sampled on
a regular pixel grid (e.g. every 100 px) -- derived from the same
uncorrected spacecraft pointing as the image itself. We use it only to find
an approximate (line, sample) window covering an AOI, so a huge orbit strip
(hundreds of thousands of lines) can be windowed down to a manageable crop
before any pixel-level processing. It is a seed for cropping, not ground
truth for registration.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio.transform import rowcol
from rasterio.windows import Window

from algo.utils.io import MOON_RADIUS_M

_MOON_GEOGRAPHIC = pyproj.CRS.from_proj4(f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")


@dataclass
class ControlGrid:
    lons: np.ndarray
    lats: np.ndarray
    samples: np.ndarray
    lines: np.ndarray


def load_geometry_grid(csv_path: str | Path) -> ControlGrid:
    lons, lats, samples, lines = [], [], [], []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            lons.append(float(row["Longitude"]))
            lats.append(float(row["Latitude"]))
            samples.append(int(row["Pixel"]))
            lines.append(int(row["Scan"]))
    return ControlGrid(np.array(lons), np.array(lats), np.array(samples), np.array(lines))


def bbox_to_window(
    grid: ControlGrid,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    margin_px: int = 200,
) -> tuple[int, int, int, int]:
    """Approximate pixel window (row_start, row_stop, col_start, col_stop)
    covering a lat/lon bbox, from whichever control points fall inside it.
    Padded by margin_px on each side since this is only a seed estimate."""
    inside = (
        (grid.lats >= lat_min) & (grid.lats <= lat_max) & (grid.lons >= lon_min) & (grid.lons <= lon_max)
    )
    if not np.any(inside):
        center_lat, center_lon = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
        dist_sq = (grid.lats - center_lat) ** 2 + (grid.lons - center_lon) ** 2
        inside = dist_sq == dist_sq.min()

    lines_in, samples_in = grid.lines[inside], grid.samples[inside]
    row_start = max(int(lines_in.min()) - margin_px, 0)
    row_stop = int(lines_in.max()) + margin_px
    col_start = max(int(samples_in.min()) - margin_px, 0)
    col_stop = int(samples_in.max()) + margin_px
    return row_start, row_stop, col_start, col_stop


def crop_source_to_aoi(
    label_path: str | Path,
    grid_csv_path: str | Path,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    margin_px: int = 200,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Windowed read of the source raster (opened via its PDS4 .xml label,
    since raw .img files have no self-describing header) covering the AOI.
    Returns (cropped_array, (row_start, row_stop, col_start, col_stop)) in the
    original full-strip pixel grid, for reference_window_for_source_window and
    for mapping a later match coordinate back into the full strip."""
    grid = load_geometry_grid(grid_csv_path)
    row_start, row_stop, col_start, col_stop = bbox_to_window(
        grid, lat_min, lat_max, lon_min, lon_max, margin_px
    )

    with rasterio.open(label_path) as ds:
        row_stop = min(row_stop, ds.height)
        col_stop = min(col_stop, ds.width)
        window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
        array = ds.read(1, window=window)

    return array, (row_start, row_stop, col_start, col_stop)


def _nearest_lonlat(grid: ControlGrid, line: int, sample: int) -> tuple[float, float]:
    dist_sq = (grid.lines - line) ** 2 + (grid.samples - sample) ** 2
    idx = int(np.argmin(dist_sq))
    return grid.lons[idx], grid.lats[idx]


def _project_wrap_safe(
    transformer: pyproj.Transformer, reference_crs, lon: float, lat: float, anchor_x: float, anchor_y: float
):
    """lon/lat -> the reference CRS's (x, y), robust to a longitude-wraparound
    mismatch: pyproj's CRS-to-CRS transform always normalizes longitude to
    (-180, 180] before applying the target CRS's projection formula --
    re-feeding it lon+-360 makes no difference, PROJ collapses them to the
    same normalized value internally. But some planetary equirectangular
    products (e.g. a LROC NAC ROI mosaic, verified on the real Tycho data)
    were built from *unwrapped* (always-increasing 0-360) longitude, so the
    wrapped and unwrapped results land a full lunar circumference apart
    (~8,000 km) in the projected CRS -- there's no way to get PROJ's own
    transform to produce the unwrapped branch.

    For an Equirectangular CRS specifically (`+proj=eqc`), apply the
    textbook forward formula ourselves with the longitude exactly as given
    (no normalization), using the CRS's own parameters so this isn't
    hardcoded to one dataset. Whichever of PROJ's result or this manual one
    lands closer to a known-good anchor in that CRS (the reference raster's
    own upper-left corner) is kept -- so a reference CRS using the standard
    wrapped convention (verified fine on the older WAC reference) is
    unaffected."""
    candidates = [transformer.transform(lon, lat)]

    params = reference_crs.to_dict()
    if params.get("proj") == "eqc":
        radius = params.get("R", MOON_RADIUS_M)
        lat_ts = math.radians(params.get("lat_ts", 0.0))
        lon_0 = params.get("lon_0", 0.0)
        lat_0 = params.get("lat_0", 0.0)
        x_0 = params.get("x_0", 0.0)
        y_0 = params.get("y_0", 0.0)
        x = radius * math.radians(lon - lon_0) * math.cos(lat_ts) + x_0
        y = radius * math.radians(lat - lat_0) + y_0
        candidates.append((x, y))

    return min(candidates, key=lambda xy: (xy[0] - anchor_x) ** 2 + (xy[1] - anchor_y) ** 2)


def reference_window_for_source_window(
    grid: ControlGrid,
    source_window: tuple[int, int, int, int],
    reference_transform,
    reference_crs,
    margin_px: int = 20,
) -> tuple[int, int, int, int]:
    """Pixel window in the REFERENCE raster covering the same ground
    footprint as a source crop window, by looking up each corner's lat/lon
    via the control grid and reprojecting into the reference's CRS. Tighter
    and shape-matched to the source swath, unlike using the reference's
    whole exported tile -- a narrow push-broom strip and a square AOI export
    otherwise overlap very little, which starves the matcher."""
    row_start, row_stop, col_start, col_stop = source_window
    transformer = pyproj.Transformer.from_crs(_MOON_GEOGRAPHIC, reference_crs, always_xy=True)
    anchor_x, anchor_y = reference_transform.c, reference_transform.f

    ref_rows, ref_cols = [], []
    for row, col in ((row_start, col_start), (row_start, col_stop), (row_stop, col_start), (row_stop, col_stop)):
        lon, lat = _nearest_lonlat(grid, row, col)
        x, y = _project_wrap_safe(transformer, reference_crs, lon, lat, anchor_x, anchor_y)
        ref_row, ref_col = rowcol(reference_transform, x, y)
        ref_rows.append(ref_row)
        ref_cols.append(ref_col)

    return (
        max(min(ref_rows) - margin_px, 0),
        max(ref_rows) + margin_px,
        max(min(ref_cols) - margin_px, 0),
        max(ref_cols) + margin_px,
    )


def crop_reference_to_window(reference_path: str | Path, window: tuple[int, int, int, int]) -> np.ndarray:
    """Windowed read of the reference raster, averaged to grayscale, over a
    (row_start, row_stop, col_start, col_stop) window. Reads up to 3 bands --
    RGB exports (e.g. QuickMap's WAC PNG) average down to grayscale, a
    single-band grayscale source (e.g. a LROC NAC mosaic GeoTIFF) is a
    no-op average over its own one band."""
    row_start, row_stop, col_start, col_stop = window
    with rasterio.open(reference_path) as ds:
        row_stop = min(row_stop, ds.height)
        col_stop = min(col_stop, ds.width)
        row_start = max(row_start, 0)
        col_start = max(col_start, 0)
        rio_window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
        band_count = min(ds.count, 3)
        bands = ds.read(list(range(1, band_count + 1)), window=rio_window)
    return bands.mean(axis=0)
