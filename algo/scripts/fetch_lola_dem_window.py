"""Cut a LOLA DEM window for a CH2 product footprint out of PGDA's cloud-hosted
GeoTIFFs, WITHOUT downloading the whole (multi-GB) file: rasterio/GDAL reads
only the needed 512x512 deflate blocks through /vsicurl/ HTTP range requests.

Sources (PGDA, public; LRO LOLA gridded DEMs, track-adjusted):
    20 m/px  https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF   (2.7 GB, 80-90S, +-304 km)
    10 m/px  https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_83S_10MPP_ADJ.TIF   (5.1 GB, 83-90S, +-216.4 km)
Both: float32, ONE band, value = surface height in METRES above the 1737400 m
reference sphere (no scale/offset tags; the file's history is "grdmath ... 1000 MUL",
i.e. km -> m), nodata = NaN, deflate, 512x512 tiles + overviews, CRS
    +proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m
which is the same projection/orientation as scripts/fetch_trek_polar_nac.py
(x = rho sin(lon), y = rho cos(lon), row increases with -y), so a LOLA window and a
Trek NAC reference share a frame.

NOTE on consumers in src/algo: illumination/dem.py (relit layer) reprojects any-CRS DEMs onto
the reference grid (NaN nodata handled, grid convergence handled) so these windows work there.
The legacy preprocessing/relief.py assumes a GEOGRAPHIC DEM (rowcol(dem_transform, lon, lat)
directly; pixel_size_m() ignores cos(lat); compares `patch == nodata`, never true for NaN), so it
cannot consume a projected DEM. Low Sun casts very long shadows (a 1 km ridge at 2 deg = ~30 km):
use --margin-km 30 if the DEM will be used to relight a 1-4 deg-Sun OHRC strip.

    python scripts/fetch_lola_dem_window.py --product <product dir | *_g_grd_*.csv> [--margin-km 10] [--res 20]
    -> data/dem/lola_80s/<product id>_LDEM_20M.tif      (--res 10 -> data/dem/lola_83s/<id>_LDEM_10M.tif)
    -> data/raw/lro_reference/_checks/<product id>_ldem_<res>m.png  (hillshade + footprint outline)
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import cv2
import numpy as np
import rasterio
from rasterio.env import Env
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).parent))
from fetch_trek_polar_nac import find_grid_csv, load_grid, lonlat_to_xy, outline_xy  # noqa: E402

BASE = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
SOURCES = {
    20: ("LDEM_80S_20MPP_ADJ.TIF", "lola_80s", "20M"),
    10: ("LDEM_83S_10MPP_ADJ.TIF", "lola_83s", "10M"),
}
DATA = Path(__file__).parents[2] / "data"
GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF",
    GDAL_HTTP_MAX_RETRY="6",
    GDAL_HTTP_RETRY_DELAY="3",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    VSI_CACHE="TRUE",
    VSI_CACHE_SIZE="268435456",
    CPL_VSIL_CURL_CACHE_SIZE="268435456",
)


def hillshade(dem: np.ndarray, res: float, az: float = 315.0, alt: float = 25.0) -> np.ndarray:
    z = np.nan_to_num(dem, nan=float(np.nanmedian(dem)))
    dzdy, dzdx = np.gradient(z, res)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(dzdy, -dzdx)
    azr, altr = np.radians(az), np.radians(alt)
    hs = np.sin(altr) * np.cos(slope) + np.cos(altr) * np.sin(slope) * np.cos(azr - aspect)
    return np.clip(hs * 255, 0, 255).astype(np.uint8)


def fetch(product: str, margin_km: float = 10.0, res: int = 20) -> Path:
    fname, subdir, tag = SOURCES[res]
    csv = find_grid_csv(product)
    lon, lat, pix, scan = load_grid(csv)
    pid = csv.name.split("_g_grd")[0] + "_d_img_d18"
    x, y = lonlat_to_xy(lon, lat)
    m = margin_km * 1000
    with Env(**GDAL_ENV), rasterio.open("/vsicurl/" + BASE + fname) as src:
        left, top, px = src.transform.c, src.transform.f, src.transform.a
        c0, c1 = int(np.floor((x.min() - m - left) / px)), int(np.ceil((x.max() + m - left) / px))
        r0, r1 = int(np.floor((top - (y.max() + m)) / px)), int(np.ceil((top - (y.min() - m)) / px))
        c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, src.width), min(r1, src.height)
        print(f"{pid}: window cols {c0}:{c1} rows {r0}:{r1} = {c1 - c0}x{r1 - r0} px @ {px:g} m "
              f"(~{(c1 - c0) * (r1 - r0) * 4 / 1e6:.0f} MB float32)")
        dem = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
        transform = src.window_transform(Window(c0, r0, c1 - c0, r1 - r0))
        crs = src.crs
        src_nodata = src.nodata
    nan_frac = float(np.isnan(dem).mean())
    print(f"  height range {np.nanmin(dem):.1f} .. {np.nanmax(dem):.1f} m, NaN fraction {nan_frac:.4f} (source nodata={src_nodata})")

    out = DATA / "dem" / subdir / f"{pid}_LDEM_{tag}.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out, "w", driver="GTiff", height=dem.shape[0], width=dem.shape[1], count=1, dtype="float32",
        crs=crs, transform=transform, nodata=np.nan, compress="deflate", predictor=3, tiled=True,
        blockxsize=256, blockysize=256,
    ) as ds:
        ds.write(dem.astype(np.float32), 1)
        ds.update_tags(SOURCE=BASE + fname, UNITS="metres above 1737400 m sphere", FOOTPRINT_MARGIN_KM=str(margin_km))
        ds.set_band_description(1, "LOLA surface height [m] above R=1737400 m sphere")
    print(f"  wrote {out}")

    # hillshade + footprint outline check image
    chk = DATA / "raw" / "lro_reference" / "_checks" / f"{pid}_ldem_{tag.lower()}.png"
    hs = hillshade(dem, px)
    sc = min(1.0, 1400 / max(hs.shape))
    vis = cv2.cvtColor(cv2.resize(hs, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    ox, oy = outline_xy(lon, lat, pix, scan)
    pts = np.stack([(ox - transform.c) / transform.a * sc, (oy - transform.f) / transform.e * sc], 1).astype(np.int32)
    cv2.polylines(vis, [pts], True, (0, 0, 255), 2)
    cv2.putText(vis, f"{pid[:34]} LOLA {tag} hillshade", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.imwrite(str(chk), vis)
    print(f"  wrote {chk}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--product", nargs="+", required=True, help="CH2 product dir(s) or *_g_grd_*.csv")
    ap.add_argument("--margin-km", type=float, default=10.0)
    ap.add_argument("--res", type=int, choices=sorted(SOURCES), default=20, help="20 (80S, default) or 10 (83S)")
    a = ap.parse_args(argv)
    for p in a.product:
        fetch(p, a.margin_km, a.res)


if __name__ == "__main__":
    sys.exit(main())
