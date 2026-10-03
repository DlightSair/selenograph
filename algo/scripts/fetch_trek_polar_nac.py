"""Build a map-projected polar reference GeoTIFF (default: LRO LROC NAC *south*-polar
mosaic) from NASA Moon Trek's public WMTS tiles.

Default layer  nac_avg = LRO_NAC_AvgMosaic_SPole855_1mp. It only covers latitude < -85.5 deg
(a +-136.5 km square around the pole) and Trek serves its tile pyramid only down to
zoom 11 (4.18 m/px; z12+ return 404) even though the mosaic is nominally 1 m/px.
`--layer nac_1m` (LRO_NAC_Mosaic_1mpp_SP) is served to zoom 12 = 2.09 m/px (same footprint).
Other polar layers (see LAYERS / `--list-layers`) cover lower latitudes at coarser scale:
WAC 100 m (tiles only to 267 m/px), Chang'e-2 7 m (tiles to 16.7 m/px), NAC PSR 20 m (to 33 m/px).

Tile grid (verified against each layer's WMTSCapabilities.xml; identical for all layers):
    TopLeftCorner = (-1095930, +1095930) m, 256-px tiles,
    metres/px at zoom z = 2191860 / 256 / 2**z = 8561.953 / 2**z,
    tile (row, col) covers x = -1095930 + col*256*res .. , y = 1095930 - row*256*res .. downward.
    The pole is the centre of tile (2**(z-1), 2**(z-1)).

Projection and orientation (checked against known south-pole craters; the other 7 mirror/rotation variants do not fit):
    polar stereographic on a sphere R = 1737400 m, k = 1 at the pole,
    south:  rho = 2 R tan((90 + lat)/2),  x = rho sin(lon),  y = +rho cos(lon)
            == PROJ  +proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=1737400 +units=m
    north:  rho = 2 R tan((90 - lat)/2),  x = rho sin(lon),  y = -rho cos(lon)
            == PROJ  +proj=stere +lat_0=+90 +lon_0=0 +k=1 +R=1737400 +units=m
    (lon east-positive). Image column increases with +x, image row increases with -y.
    South: lon 0 deg points toward the TOP of the image, lon 90E to the RIGHT.
    North: lon 0 deg points toward the BOTTOM of the image, lon 90E to the RIGHT.

Usage (paths are resolved relative to this file, so cwd does not matter):

    # footprint from a CH2 product's control grid (+ margin, default 3 km)
    python scripts/fetch_trek_polar_nac.py --product <product dir | *_g_grd_*.csv> [--name NAME] [--margin-km 3]

    # footprint from an explicit lat,lon points list (bbox of the points + margin)
    python scripts/fetch_trek_polar_nac.py --name NAME --latlon -86.3,60 -86.1,61.5 [--margin-km 3]

    # a lat/lon box (dense edge sampling -> xy bbox, + margin)
    python scripts/fetch_trek_polar_nac.py --name NAME --layer ce2_np --aoi LAT_MIN LAT_MAX LON_MIN LON_MAX

    # Raw products have no control grid: footprint = the 4 System_Level corner coordinates of the label
    python scripts/fetch_trek_polar_nac.py --product <raw product dir> --layer ce2_np

    # restrict a very long strip to a stretch (fractions of its along-track length, e.g. the middle 10%)
    python scripts/fetch_trek_polar_nac.py --product <dir> --layer ce2_np --segment 0.45 0.55 --margin-km 8

    -> data/raw/lro_reference/<name>/<subdir>/<name>_<SUFFIX>.tif   (single-band uint8, nodata=0;
       default layer: <name>/nac/<name>_NAC_SP.tif)
    -> data/raw/lro_reference/_checks/<name>_<layer>_footprint.png   (footprint outline drawn on it)

Output pixels: 0 = no data (outside the layer's coverage / no tile); valid pixels are clipped to
>= 1 so 0 is unambiguous.
"""

from __future__ import annotations

import argparse
import glob
import math
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

MOON_R = 1_737_400.0
X0, Y0 = -1_095_930.0, 1_095_930.0  # TopLeftCorner of the tile matrix (all layers)
TILE_SPAN_Z0 = 2_191_860.0  # metres covered by one 256-px tile at z0
ROOT = Path(__file__).parents[2] / "data" / "raw" / "lro_reference"
USER_AGENT = "sih26166-reference-builder/1.0 (research; polite, cached)"
TILE_URL = "https://trek.nasa.gov/tiles/Moon/{region}/{label}/1.0.0/default/default028mm/{z}/{r}/{c}.png"

# key -> region (SP/NP), Trek layer id, max served zoom, layer bbox (xmin, ymin, xmax, ymax) in polar metres
# (from each layer's WMTSCapabilities.xml), output subdir and file suffix.
LAYERS = {
    "nac_avg": dict(region="SP", label="LRO_NAC_AvgMosaic_SPole855_1mp", zmax=11, bbox=(-136526, -136525, 136525, 136526), subdir="nac", suffix="NAC_SP"),
    "nac_1m": dict(region="SP", label="LRO_NAC_Mosaic_1mpp_SP", zmax=12, bbox=(-136716.373, -136875.424, 136862.627, 136745.576), subdir="nac", suffix="NAC1M_SP"),
    "psr_sp": dict(region="SP", label="NAC_POLE_PSR_SOUTH_STRETCH", zmax=8, bbox=(-304010, -320470, 304010, 304010), subdir="nacpsr", suffix="NACPSR_SP"),
    "ce2_sp": dict(region="SP", label="CE2_OrthoMosaic_7m_SP", zmax=9, bbox=(-931069.792, -931070.153, 931077.208, 931069.847), subdir="ce2", suffix="CE2_SP"),
    "wac_sp": dict(region="SP", label="LRO_WAC_Mosaic_SPole60_100m_v02", zmax=5, bbox=(-1095700, -1095600, 1095600, 1095700), subdir="wacpolar", suffix="WACPOLAR_SP"),
    "lo_sp": dict(region="SP", label="LO_HRMR_Mosaic_SPole70_59mp", zmax=5, bbox=(-612685.728, -612685.729, 612685.729, 612685.728), subdir="lo", suffix="LO_SP"),
    "nac_avg_np": dict(region="NP", label="LRO_NAC_AvgMosaic_NPole855_1mp", zmax=11, bbox=(-136526, -136526, 136526, 136526), subdir="nac", suffix="NAC_NP"),
    "psr_np": dict(region="NP", label="NAC_POLE_PSR_NORTH_STRETCH", zmax=8, bbox=(-304010, -304025.323, 304010, 320454.677), subdir="nacpsr", suffix="NACPSR_NP"),
    "ce2_np": dict(region="NP", label="CE2_OrthoMosaic_7m_NP", zmax=9, bbox=(-931072.592, -931073.755, 931081.408, 931073.245), subdir="ce2", suffix="CE2_NP"),
    "wac_np": dict(region="NP", label="LRO_WAC_Mosaic_NPole60_100m_v02", zmax=5, bbox=(-1095700, -1095600, 1095600, 1095700), subdir="wacpolar", suffix="WACPOLAR_NP"),
    "lo_np": dict(region="NP", label="LO_HRMR_Mosaic_NPole70_59mp", zmax=5, bbox=(-612744.954, -612685.728, 612685.728, 612744.954), subdir="lo", suffix="LO_NP"),
}
DEFAULT_LAYER = "nac_avg"


def crs_for(region: str) -> CRS:
    lat0 = -90 if region == "SP" else 90
    return CRS.from_proj4(f"+proj=stere +lat_0={lat0} +lon_0=0 +k=1 +R={int(MOON_R)} +units=m +no_defs")


# ---------------------------------------------------------------- projection
def lonlat_to_xy(lon, lat, region: str = "SP"):
    """lon (deg east, any wrap), lat (deg) -> polar stereographic metres (see module docstring)."""
    lon, lat = np.radians(np.asarray(lon, float)), np.asarray(lat, float)
    if region == "SP":
        rho = 2 * MOON_R * np.tan(np.radians(90.0 + lat) / 2)
        return rho * np.sin(lon), rho * np.cos(lon)
    rho = 2 * MOON_R * np.tan(np.radians(90.0 - lat) / 2)
    return rho * np.sin(lon), -rho * np.cos(lon)


def xy_to_lonlat(x, y, region: str = "SP"):
    x, y = np.asarray(x, float), np.asarray(y, float)
    rho = np.hypot(x, y)
    colat = 2 * np.degrees(np.arctan(rho / (2 * MOON_R)))
    if region == "SP":
        return np.degrees(np.arctan2(x, y)) % 360, -90.0 + colat
    return np.degrees(np.arctan2(x, -y)) % 360, 90.0 - colat


# ---------------------------------------------------------------- tiles
def res_at(z: int) -> float:
    return TILE_SPAN_Z0 / 256 / 2**z


def tile_range(layer: dict, z: int) -> tuple[int, int, int, int]:
    """(row_lo, row_hi, col_lo, col_hi) of tiles intersecting the layer bbox at zoom z."""
    xmin, ymin, xmax, ymax = layer["bbox"]
    span = 256 * res_at(z)
    return (math.floor((Y0 - ymax) / span), math.floor((Y0 - ymin) / span),
            math.floor((xmin - X0) / span), math.floor((xmax - X0) / span))


def _fetch_tile(layer: dict, z: int, row: int, col: int) -> np.ndarray | None:
    """RGBA uint8 (256, 256, 4) or None if the server has no tile. Cached on disk
    (an empty cache file records a 404)."""
    cache = ROOT / "_tiles" / f"trek_{layer['label']}_z{z}" if layer["label"] != "LRO_NAC_AvgMosaic_SPole855_1mp" \
        else ROOT / "_tiles" / f"trek_sp_z{z}"
    cache = cache / f"{row}_{col}.png"
    if cache.exists():
        data = cache.read_bytes()
        if not data:
            return None
    else:
        cache.parent.mkdir(parents=True, exist_ok=True)
        url = TILE_URL.format(region=layer["region"], label=layer["label"], z=z, r=row, c=col)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        data = None
        for attempt in range(8):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    cache.write_bytes(b"")
                    return None
                time.sleep(1.5 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                time.sleep(1.5 * (attempt + 1))  # server drops connections under load -> back off
        if data is None:
            raise RuntimeError(f"tile {layer['label']} z{z}/{row}/{col} failed after retries")
        cache.write_bytes(data)
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        img = np.dstack([img, img, img, np.full_like(img, 255)])
    elif img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return img


def build_window(layer: dict, z: int, x_min: float, x_max: float, y_min: float, y_max: float, workers: int = 4):
    """Pixel-aligned window of the zoom-z mosaic covering the xy bbox -> (uint8 array, Affine)."""
    res = res_at(z)
    c0, c1 = math.floor((x_min - X0) / res), math.ceil((x_max - X0) / res)
    r0, r1 = math.floor((Y0 - y_max) / res), math.ceil((Y0 - y_min) / res)
    rlo, rhi, clo, chi = tile_range(layer, z)
    tc0, tc1 = max(c0 // 256, clo), min((c1 - 1) // 256, chi)
    tr0, tr1 = max(r0 // 256, rlo), min((r1 - 1) // 256, rhi)
    jobs = [(r, c) for r in range(tr0, tr1 + 1) for c in range(tc0, tc1 + 1)]
    print(f"{layer['label']} zoom {z} ({res:.3f} m/px): window {c1 - c0}x{r1 - r0}px, fetching {len(jobs)} tiles ({workers} workers)")
    out = np.zeros((r1 - r0, c1 - c0), np.uint8)
    if jobs:
        with ThreadPoolExecutor(workers) as pool:
            tiles = list(pool.map(lambda rc: _fetch_tile(layer, z, *rc), jobs))
        for (r, c), t in zip(jobs, tiles):
            if t is None:
                continue
            gray = np.where(t[..., 3] > 0, np.maximum(t[..., 0], 1), 0).astype(np.uint8)
            gr0, gc0 = r * 256, c * 256
            ra, rb = max(gr0, r0), min(gr0 + 256, r1)
            ca, cb = max(gc0, c0), min(gc0 + 256, c1)
            if ra < rb and ca < cb:
                out[ra - r0:rb - r0, ca - c0:cb - c0] = gray[ra - gr0:rb - gr0, ca - gc0:cb - gc0]
    return out, Affine(res, 0, X0 + c0 * res, 0, -res, Y0 - r0 * res)


# ---------------------------------------------------------------- footprints
def find_grid_csv(path: str | Path) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    hits = sorted(glob.glob(str(p / "geometry" / "**" / "*_g_grd_*.csv"), recursive=True))
    if not hits:
        raise FileNotFoundError(f"no *_g_grd_*.csv control grid under {p}")
    return Path(hits[0])


def load_grid(csv_path: Path):
    a = np.genfromtxt(csv_path, delimiter=",", names=True)
    return a["Longitude"], a["Latitude"], a["Pixel"], a["Scan"]


def outline_xy(lon, lat, pix, scan, region: str = "SP"):
    """Closed outline (left edge down, right edge up) of a control grid, in polar xy."""
    left = np.flatnonzero(pix == pix.min())
    left = left[np.argsort(scan[left])]
    right = np.flatnonzero(pix == pix.max())
    right = right[np.argsort(-scan[right])]
    idx = np.concatenate([left, right])
    return lonlat_to_xy(lon[idx], lat[idx], region)


def label_corners(product: str | Path):
    """(lon[4], lat[4]) UL, UR, LR, LL from the label's System_Level_Coordinates (raw products)."""
    xmls = sorted(glob.glob(str(Path(product) / "data" / "**" / "*.xml"), recursive=True))
    if not xmls:
        raise FileNotFoundError(f"no data label under {product}")
    txt = Path(xmls[0]).read_text(errors="ignore")
    blk = re.search(r"<isda:System_Level_Coordinates>(.*?)</isda:System_Level_Coordinates>", txt, re.S).group(1)
    get = lambda tag: float(re.search(rf"<isda:{tag}[^>]*>\s*([-0-9.]+)\s*<", blk).group(1))
    names = ["upper_left", "upper_right", "lower_right", "lower_left"]
    return (np.array([get(f"{n}_longitude") for n in names]), np.array([get(f"{n}_latitude") for n in names]))


def corner_segment(lon, lat, region, f0, f1):
    """Sub-quad of the UL,UR,LR,LL corner quadrilateral between along-track fractions f0..f1
    (bilinear in the projection plane) -> (x[4], y[4])."""
    x, y = lonlat_to_xy(lon, lat, region)
    ul, ur, lr, ll = (np.array([x[i], y[i]]) for i in range(4))
    at = lambda f: (ul + f * (ll - ul), ur + f * (lr - ur))
    (a0, b0), (a1, b1) = at(f0), at(f1)
    q = np.array([a0, b0, b1, a1])
    return q[:, 0], q[:, 1]


def densify(x, y, n=40):
    """Closed polygon through (x, y) with n points per edge (straight in the projection plane)."""
    px, py = [], []
    for i in range(len(x)):
        j = (i + 1) % len(x)
        px.append(np.linspace(x[i], x[j], n, endpoint=False))
        py.append(np.linspace(y[i], y[j], n, endpoint=False))
    return np.concatenate(px), np.concatenate(py)


def aoi_outline(lat_min, lat_max, lon_min, lon_max, region, n=60):
    lons = np.concatenate([np.linspace(lon_min, lon_max, n), np.full(n, lon_max), np.linspace(lon_max, lon_min, n), np.full(n, lon_min)])
    lats = np.concatenate([np.full(n, lat_min), np.linspace(lat_min, lat_max, n), np.full(n, lat_max), np.linspace(lat_max, lat_min, n)])
    return lonlat_to_xy(lons, lats, region)


def default_name(product: str) -> str:
    m = re.search(r"ch2_(\w+?)_\w+?_(\d{8})T(\d{4})", Path(product).name)
    if m:
        inst = {"ohr": "ohrc", "tmc": "tmc"}.get(m.group(1), m.group(1))
        return f"{inst}_{m.group(2)}"
    return Path(product).stem


# ---------------------------------------------------------------- main
def build(name: str, layer_key: str, x, y, outline=None, margin_km: float = 3.0, zoom: int | None = None,
          workers: int = 4) -> Path:
    layer = LAYERS[layer_key]
    zoom = layer["zmax"] if zoom is None else min(zoom, layer["zmax"])
    region = layer["region"]
    m = margin_km * 1000
    x_min, x_max, y_min, y_max = np.min(x) - m, np.max(x) + m, np.min(y) - m, np.max(y) + m
    bx0, by0, bx1, by1 = layer["bbox"]
    inside = float(np.mean((np.asarray(x) >= bx0) & (np.asarray(x) <= bx1) & (np.asarray(y) >= by0) & (np.asarray(y) <= by1)))
    print(f"{name} [{layer_key}]: {100 * inside:.1f}% of footprint points inside the layer bbox")
    if inside == 0:
        raise SystemExit(f"footprint lies entirely outside layer {layer['label']}: nothing to build")

    out, transform = build_window(layer, zoom, x_min, x_max, y_min, y_max, workers)
    path = ROOT / name / layer["subdir"] / f"{name}_{layer['suffix']}.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", height=out.shape[0], width=out.shape[1], count=1, dtype="uint8",
        crs=crs_for(region), transform=transform, nodata=0, compress="deflate", tiled=True, blockxsize=256, blockysize=256,
    ) as ds:
        ds.write(out, 1)
        ds.update_tags(SOURCE=f"NASA Moon Trek WMTS {layer['label']} z{zoom}", PIXEL_M=f"{res_at(zoom):.4f}",
                       CONVENTION="x=rho*sin(lon) y=%srho*cos(lon) polar stereographic R=1737400" % ("" if region == "SP" else "-"))
    print(f"wrote {path} ({out.shape[1]}x{out.shape[0]}px @ {res_at(zoom):.3f} m/px, {100 * float((out > 0).mean()):.1f}% valid pixels)")

    check = ROOT / "_checks" / f"{name}_{layer_key}_footprint.png"
    check.parent.mkdir(parents=True, exist_ok=True)
    scale = min(1.0, 1600 / max(out.shape))
    small = cv2.resize(out, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    vis = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    ox, oy = outline if outline is not None else (x, y)
    px = ((np.asarray(ox) - transform.c) / transform.a * scale).astype(np.int32)
    py = ((np.asarray(oy) - transform.f) / transform.e * scale).astype(np.int32)
    cv2.polylines(vis, [np.stack([px, py], 1)], outline is not None, (0, 0, 255), 2)
    top = "lon0 = up, lon90E = right" if region == "SP" else "lon0 = down, lon90E = right"
    cv2.putText(vis, f"{name} {layer['label'][:28]} z{zoom} {res_at(zoom):.2f} m/px ({top})", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.imwrite(str(check), vis)
    print(f"wrote {check}")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--product", help="CH2 product dir (or its *_g_grd_*.csv); footprint = all control-grid points "
                                      "(raw products without a grid: the label's 4 System_Level corners)")
    ap.add_argument("--name", help="output name (default derived from the product id, e.g. ohrc_20260721)")
    ap.add_argument("--layer", default=DEFAULT_LAYER, choices=sorted(LAYERS))
    ap.add_argument("--list-layers", action="store_true")
    ap.add_argument("--latlon", nargs="+", help="explicit 'lat,lon' points (lon east, 0..360 or -180..180)")
    ap.add_argument("--aoi", nargs=4, type=float, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"))
    ap.add_argument("--segment", nargs=2, type=float, metavar=("F0", "F1"),
                    help="with --product: keep only this fraction range (0..1) of the strip's along-track length")
    ap.add_argument("--margin-km", type=float, default=3.0)
    ap.add_argument("--zoom", type=int, default=None, help="tile zoom (default = finest served for the layer)")
    ap.add_argument("--workers", type=int, default=4, help="parallel tile downloads (be polite; server drops many)")
    a = ap.parse_args(argv)

    if a.list_layers:
        for k, v in LAYERS.items():
            print(f"{k:10s} {v['region']} {v['label']:36s} zmax {v['zmax']:2d} ({res_at(v['zmax']):7.2f} m/px) -> {v['subdir']}/<name>_{v['suffix']}.tif")
        return
    region = LAYERS[a.layer]["region"]
    if a.product:
        try:
            csv = find_grid_csv(a.product)
            lon, lat, pix, scan = load_grid(csv)
            if a.segment:
                keep = (scan >= a.segment[0] * scan.max()) & (scan <= a.segment[1] * scan.max())
                lon, lat, pix, scan = lon[keep], lat[keep], pix[keep], scan[keep]
            name = a.name or default_name(csv.name)
            x, y = lonlat_to_xy(lon, lat, region)
            build(name, a.layer, x, y, outline_xy(lon, lat, pix, scan, region), a.margin_km, a.zoom, a.workers)
        except FileNotFoundError:
            lon, lat = label_corners(a.product)
            name = a.name or default_name(Path(a.product).name)
            if a.segment:
                x, y = corner_segment(lon, lat, region, *a.segment)
            else:
                x, y = lonlat_to_xy(lon, lat, region)
            print("raw product: footprint from the 4 System_Level corners (straight edges in the projection plane)")
            clon, clat = xy_to_lonlat(x.mean(), y.mean(), region)
            print(f"  footprint centre lat {float(clat):.3f} lon {float(clon):.3f}")
            build(name, a.layer, x, y, densify(x, y), a.margin_km, a.zoom, a.workers)
    elif a.aoi and a.name:
        x, y = aoi_outline(*a.aoi, region)
        build(a.name, a.layer, x, y, (x, y), a.margin_km, a.zoom, a.workers)
    elif a.latlon and a.name:
        pts = np.array([[float(v) for v in s.split(",")] for s in a.latlon])
        x, y = lonlat_to_xy(pts[:, 1], pts[:, 0], region)
        build(a.name, a.layer, x, y, None, a.margin_km, a.zoom, a.workers)
    else:
        ap.error("give --product, or --name together with --aoi / --latlon")


if __name__ == "__main__":
    sys.exit(main())
