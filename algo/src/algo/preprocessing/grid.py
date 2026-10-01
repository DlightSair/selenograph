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
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window


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
) -> tuple[np.ndarray, tuple[int, int]]:
    """Windowed read of the source raster (opened via its PDS4 .xml label,
    since raw .img files have no self-describing header) covering the AOI.
    Returns (cropped_array, (row_offset, col_offset)) -- the offset lets a
    later pixel coordinate be mapped back into the original full strip."""
    grid = load_geometry_grid(grid_csv_path)
    row_start, row_stop, col_start, col_stop = bbox_to_window(
        grid, lat_min, lat_max, lon_min, lon_max, margin_px
    )

    with rasterio.open(label_path) as ds:
        row_stop = min(row_stop, ds.height)
        col_stop = min(col_stop, ds.width)
        window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
        array = ds.read(1, window=window)

    return array, (row_start, col_start)
