"""Build a map-projected LRO WAC reference GeoTIFF for a lat/lon box from NASA
Moon Trek's public WMTS tiles (LRO WAC global mosaic, 303 ppd ~ 100 m/px).

Output matches the convention of the existing NAC ROI mosaics: single-band
uint8 GeoTIFF in a local Equirectangular CRS (square metre pixels, centred on
the box), so it drops straight into `reference.path` of a project config.

    python scripts/fetch_wac_reference.py <name> <lat_min> <lat_max> <lon_min> <lon_max>
    -> data/raw/lro_reference/<name>/wac/<name>_WAC_100M.tif

100 m/px is far coarser than the ~5 m/px TMC-2 source, so this is a *coarse*
reference: fine for validating and anchoring a registration, not for
sub-10 m accuracy. A NAC mosaic (LROC ROI products) is better where one exists.
"""

from __future__ import annotations

import math
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pyproj
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

MOON_R = 1_737_400
ZOOM = 8  # 256 * 2**8 / 180 = 364 ppd, a bit above the mosaic's native 303 ppd
URL = "https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{r}/{c}.jpg"
ROOT = Path(__file__).parents[2] / "data" / "raw" / "lro_reference"


def _tile(z: int, row: int, col: int) -> np.ndarray:
    cache = ROOT / "_tiles" / f"wac_z{z}" / f"{row}_{col}.jpg"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL.format(z=z, r=row, c=col), timeout=60) as resp:
            cache.write_bytes(resp.read())
    img = cv2.imdecode(np.frombuffer(cache.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    return img if img is not None else np.zeros((256, 256), np.uint8)


def build(name: str, lat_min: float, lat_max: float, lon_min: float, lon_max: float, pixel_m: float = 100.0) -> Path:
    span = 180.0 / 2**ZOOM  # degrees per tile
    lon_w = lon_min - 360 if lon_min > 180 else lon_min  # tiles use -180..180
    lon_e = lon_max - 360 if lon_max > 180 else lon_max
    col0, col1 = int((lon_w + 180) // span), int((lon_e + 180) // span)
    row0, row1 = int((90 - lat_max) // span), int((90 - lat_min) // span)
    jobs = [(r, c) for r in range(row0, row1 + 1) for c in range(col0, col1 + 1)]
    print(f"fetching {len(jobs)} WAC tiles (zoom {ZOOM})")
    with ThreadPoolExecutor(8) as pool:
        tiles = dict(zip(jobs, pool.map(lambda rc: _tile(ZOOM, *rc), jobs)))

    mosaic = np.zeros(((row1 - row0 + 1) * 256, (col1 - col0 + 1) * 256), np.uint8)
    for (r, c), t in tiles.items():
        mosaic[(r - row0) * 256:(r - row0 + 1) * 256, (c - col0) * 256:(c - col0 + 1) * 256] = t
    ppd = 256 / span
    src_transform = from_origin(col0 * span - 180, 90 - row0 * span, 1 / ppd, 1 / ppd)
    geographic = CRS.from_proj4(f"+proj=longlat +R={MOON_R} +no_defs")

    lat_c = (lat_min + lat_max) / 2
    lon_c = (lon_min + lon_max) / 2
    eqc = CRS.from_proj4(
        f"+proj=eqc +lat_ts={lat_c:.4f} +lat_0=0 +lon_0={lon_c:.4f} +x_0=0 +y_0=0 +R={MOON_R} +units=m +no_defs"
    )
    to_xy = pyproj.Transformer.from_crs(geographic, eqc, always_xy=True)
    lons = np.linspace(lon_w, lon_e, 9)
    lats = np.linspace(lat_min, lat_max, 9)
    xs, ys = to_xy.transform(*np.meshgrid(lons, lats))
    xmin, xmax, ymin, ymax = xs.min(), xs.max(), ys.min(), ys.max()
    width, height = math.ceil((xmax - xmin) / pixel_m), math.ceil((ymax - ymin) / pixel_m)
    dst_transform = from_origin(xmin, ymax, pixel_m, pixel_m)

    out = np.zeros((height, width), np.uint8)
    reproject(
        mosaic, out, src_transform=src_transform, src_crs=geographic,
        dst_transform=dst_transform, dst_crs=eqc, resampling=Resampling.cubic,
    )
    path = ROOT / name / "wac" / f"{name}_WAC_100M.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1, dtype="uint8",
        crs=eqc, transform=dst_transform, nodata=0, compress="deflate",
    ) as ds:
        ds.write(out, 1)
    print(f"wrote {path} ({width}x{height}px @ {pixel_m:.0f} m/px)")
    return path


if __name__ == "__main__":
    n, *vals = sys.argv[1:]
    build(n, *map(float, vals))
