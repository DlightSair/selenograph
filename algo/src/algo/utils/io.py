"""Shared raster/label IO helpers used across stages."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

MOON_RADIUS_M = 1_737_400

_PDS4_DATA_EXTS = {".tif", ".tiff", ".img", ".qub"}


def find_pds4_product(product_dir: str | Path) -> tuple[Path, Path]:
    """Locate the data file and matching .xml label inside an ISSDC PDS4 product
    bundle, e.g. <id>/data/derived/<date>/<id>.tif + <id>.xml (same layout for
    OHRC/TMC-2/IIRS/DTM products)."""
    product_dir = Path(product_dir)
    candidates = sorted(p for p in product_dir.rglob("*") if p.suffix.lower() in _PDS4_DATA_EXTS)
    if not candidates:
        raise FileNotFoundError(f"no PDS4 data file (.tif/.img/.qub) found under {product_dir}")
    data_path = candidates[0]
    label_path = data_path.with_suffix(".xml")
    if not label_path.exists():
        raise FileNotFoundError(f"no matching .xml label for {data_path}")
    return data_path, label_path


def read_raster(path: str | Path, band: int = 1) -> tuple[np.ndarray, Affine, rasterio.crs.CRS | None]:
    """Read one band of a raster plus its affine transform and CRS. CRS is None
    for Chandrayaan-2 Calibrated products, which aren't map-projected yet."""
    with rasterio.open(path) as ds:
        return ds.read(band), ds.transform, ds.crs


def write_raster(path: str | Path, array: np.ndarray, transform: Affine, crs) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        transform=transform,
        crs=crs,
    ) as ds:
        ds.write(array, 1)


def pixel_size_m(transform: Affine, crs: rasterio.crs.CRS | None) -> tuple[float, float]:
    """(dx, dy) pixel size in metres, converting from degrees via the lunar
    radius when the CRS is geographic (e.g. the Selenographic DEM/ortho CRS)."""
    dx, dy = abs(transform.a), abs(transform.e)
    if crs is not None and crs.is_geographic:
        dx = math.radians(dx) * MOON_RADIUS_M
        dy = math.radians(dy) * MOON_RADIUS_M
    return dx, dy
