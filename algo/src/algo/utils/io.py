"""Shared raster/label IO helpers used across stages."""

from __future__ import annotations

import math
from pathlib import Path

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


def pixel_size_m(transform: Affine, crs: rasterio.crs.CRS | None) -> tuple[float, float]:
    """(dx, dy) pixel size in metres, converting from degrees via the lunar
    radius when the CRS is geographic (e.g. the Selenographic DEM/ortho CRS)."""
    dx, dy = abs(transform.a), abs(transform.e)
    if crs is not None and crs.is_geographic:
        dx = math.radians(dx) * MOON_RADIUS_M
        dy = math.radians(dy) * MOON_RADIUS_M
    return dx, dy
