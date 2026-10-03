"""Deliverables of a registration run beyond the transform itself:

  registered.tif     the source resampled into the reference raster's pixel grid by the *full* model
                     (homography + DEM parallax + non-rigid field), georeferenced in the reference CRS;
                     nodata (0) where the source has no coverage.
  tiepoints_geo.csv  the inlier correspondences as georeferenced tie points: source line/sample of the
                     original product <-> reference x/y in the reference CRS <-> lon/lat (east-positive,
                     0..360) -- loadable as GCPs in GIS software.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio.transform import Affine

from algo.utils.io import MOON_RADIUS_M

_MOON_GEOGRAPHIC = pyproj.CRS.from_proj4(f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")


def write_registered_geotiff(path: Path, model_local, source_crop: np.ndarray, source_to_full: np.ndarray,
                             ref_shape: tuple[int, int], ref_transform: Affine, ref_crs, row_off: int, col_off: int) -> None:
    """`model_local` maps full-resolution source-crop px to reference-crop-local px; `source_crop` may be
    decimated (`source_to_full` maps its pixels to full-resolution ones)."""
    warped, valid = model_local.with_source_matrix(source_to_full).warp_source(source_crop, ref_shape)
    warped = np.where(valid, np.maximum(warped, 1e-3), 0.0).astype(np.float32)  # 0 is reserved for "no data"
    transform = ref_transform * Affine.translation(col_off, row_off)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=ref_shape[0], width=ref_shape[1], count=1, dtype="float32",
                       crs=ref_crs, transform=transform, nodata=0.0, compress="deflate", zlevel=1, predictor=3, tiled=True,
                       blockxsize=256, blockysize=256) as ds:
        ds.write(warped, 1)


def write_tiepoints_geo(path: Path, inliers: list, ref_transform: Affine, ref_crs, source_window: tuple[int, int, int, int]) -> None:
    """`inliers`: Match objects with source xy in full-res crop px and reference xy in absolute reference-raster px."""
    to_geo = pyproj.Transformer.from_crs(ref_crs, _MOON_GEOGRAPHIC, always_xy=True)
    row_start, _, col_start, _ = source_window
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_line", "source_sample", "reference_x", "reference_y", "lon_deg_e", "lat_deg", "confidence"])
        for m in inliers:
            x, y = ref_transform * (m.reference_xy[0] + 0.5, m.reference_xy[1] + 0.5)
            lon, lat = to_geo.transform(x, y)
            w.writerow([f"{m.source_xy[1] + row_start:.2f}", f"{m.source_xy[0] + col_start:.2f}", f"{x:.3f}", f"{y:.3f}",
                        f"{lon % 360.0:.7f}", f"{lat:.7f}", f"{m.confidence:.3f}"])
