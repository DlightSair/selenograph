"""Cut a window out of the global LOLA DEM (USGS Astrogeology, 118 m/px, simple cylindrical, int16 x 0.5 m)
by HTTP range reads -- no 8.5 GB download -- and save it as a float32 metre GeoTIFF in the same CRS.

    python scripts/fetch_lola_global_window.py <name> <lat_min> <lat_max> <lon_min> <lon_max> [--margin-deg 0.5]
    -> data/dem/lola_global/<name>_LDEM_118M.tif

Longitudes may be given 0..360 or -180..180. The margin matters when the DEM is re-lit at a low Sun
(shadows are cast from ridges outside the strip) and for terrain parallax at the window edges. The polar
south has finer 20 m / 10 m windows (`fetch_lola_dem_window.py`); this one covers everything else, poles included
at the coarser 118 m.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

URL = "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"
MOON_R = 1_737_400.0
OUT = Path(__file__).resolve().parents[2] / "data" / "dem" / "lola_global"


def fetch(name: str, lat_min: float, lat_max: float, lon_min: float, lon_max: float, margin_deg: float = 0.5) -> Path:
    wrap = lambda lon: lon - 360.0 if lon > 180.0 else lon  # noqa: E731
    lon_w, lon_e = wrap(lon_min) - margin_deg, wrap(lon_max) + margin_deg
    lat_s, lat_n = max(lat_min - margin_deg, -90.0), min(lat_max + margin_deg, 90.0)
    with rasterio.Env(GDAL_HTTP_TIMEOUT="120", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="3"):
        with rasterio.open(URL) as ds:
            tr = ds.transform
            x0, x1 = math.radians(lon_w) * MOON_R, math.radians(lon_e) * MOON_R
            y0, y1 = math.radians(lat_n) * MOON_R, math.radians(lat_s) * MOON_R
            col0, col1 = int((x0 - tr.c) / tr.a), int(math.ceil((x1 - tr.c) / tr.a))
            row0, row1 = int((tr.f - y0) / -tr.e), int(math.ceil((tr.f - y1) / -tr.e))
            col0, row0 = max(col0, 0), max(row0, 0)
            col1, row1 = min(col1, ds.width), min(row1, ds.height)
            raw = ds.read(1, window=Window(col0, row0, col1 - col0, row1 - row0))
            scale = ds.scales[0] or 1.0
            crs = ds.crs
            nodata = ds.nodata
    data = raw.astype(np.float32) * np.float32(scale)
    if nodata is not None:
        data[raw == nodata] = np.nan
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}_LDEM_118M.tif"
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1, dtype="float32", crs=crs,
                       transform=tr * Affine.translation(col0, row0), nodata=float("nan"), compress="deflate") as out:
        out.write(data, 1)
    print(f"wrote {path} {data.shape[1]}x{data.shape[0]} px, height range {np.nanmin(data):.0f}..{np.nanmax(data):.0f} m")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("lat_min", type=float)
    ap.add_argument("lat_max", type=float)
    ap.add_argument("lon_min", type=float)
    ap.add_argument("lon_max", type=float)
    ap.add_argument("--margin-deg", type=float, default=0.5)
    a = ap.parse_args()
    fetch(a.name, a.lat_min, a.lat_max, a.lon_min, a.lon_max, a.margin_deg)
