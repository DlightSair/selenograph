"""Ground-control grid for Chandrayaan-2 Calibrated products.

Calibrated OHRC/TMC-2 products are NOT map-projected (that's the whole
problem this pipeline solves), so they can't be cropped by lat/lon the way a
georeferenced raster can. Each product ships a geometry/*_g_grd_*.csv grid
alongside it -- (Longitude, Latitude, Pixel, Scan) control points sampled on
a regular pixel grid (e.g. every 100 px) -- derived from the same
uncorrected spacecraft pointing as the image itself. It is used only to find
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
from rasterio.enums import Resampling
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


def corner_control_grid(label_path: str | Path, step: int = 100) -> ControlGrid:
    """A synthetic control grid for products that ship none (RAW level: the label states only the four
    corner coordinates). Positions are bilinearly interpolated between the corners in a stereographic plane
    centred on the strip (so a strip that crosses the pole is still straight), which is good to a few km --
    a poorer prior than the product grid, so the matcher's wide-capture rescue is what makes it usable."""
    from algo.preprocessing.metadata import parse_pds4_label

    meta = parse_pds4_label(label_path)
    if not meta.footprint or len(meta.footprint) != 4 or not meta.shape:
        raise ValueError(f"{label_path}: no corner coordinates / shape in the label, cannot build a geometry")
    lines, samples = meta.shape
    lat = np.radians([c[0] for c in meta.footprint])
    lon = np.radians([c[1] for c in meta.footprint])
    vec = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1).mean(axis=0)
    lat_c = math.degrees(math.asin(vec[2] / np.linalg.norm(vec)))
    lon_c = math.degrees(math.atan2(vec[1], vec[0]))
    proj = pyproj.Proj(f"+proj=stere +lat_0={lat_c} +lon_0={lon_c} +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")
    xy = np.array([proj(c[1], c[0]) for c in meta.footprint])  # UL, UR, LR, LL
    ul, ur, lr, ll = xy

    ls = np.unique(np.append(np.arange(0, lines, step), lines - 1))
    ss = np.unique(np.append(np.arange(0, samples, max(step // 2, 25)), samples - 1))
    sg, lg = np.meshgrid(ss, ls)
    fr, fc = (lg / max(lines - 1, 1)).ravel(), (sg / max(samples - 1, 1)).ravel()
    pts = ((1 - fr)[:, None] * ((1 - fc)[:, None] * ul + fc[:, None] * ur)
           + fr[:, None] * ((1 - fc)[:, None] * ll + fc[:, None] * lr))
    lons, lats = proj(pts[:, 0], pts[:, 1], inverse=True)
    return ControlGrid(np.mod(np.asarray(lons), 360.0), np.asarray(lats), sg.ravel().astype(int), lg.ravel().astype(int))


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


def read_envi_wavelengths(label_path: str | Path) -> list[float] | None:
    """Band centres (nm) from the ENVI .hdr that sits next to a PDS4 qube (IIRS), if any."""
    import re

    hdr = Path(label_path).with_suffix(".hdr")
    if not hdr.exists():
        return None
    m = re.search(r"wavelength\s*=\s*\{([^}]*)\}", hdr.read_text(), flags=re.S)
    return [float(v) for v in " ".join(m.group(1).split()).split(",")] if m else None


def select_bands(label_path: str | Path, count: int, band_range_nm: tuple[float, float] | None) -> list[int]:
    """1-based band indexes to average into the single panchromatic image the matcher works on.
    Single-band products -> [1]. Hyperspectral cubes (IIRS, 256 bands, 0.7-5.0 um) -> the bands inside
    `band_range_nm` (default 0.9-1.6 um: solar-reflected light, good signal, no thermal emission)."""
    if count == 1:
        return [1]
    waves = read_envi_wavelengths(label_path)
    lo, hi = band_range_nm or (900.0, 1600.0)
    if waves and len(waves) == count:
        picked = [i + 1 for i, w in enumerate(waves) if lo <= w <= hi]
        if picked:
            return picked
    return list(range(1, count + 1))[: max(1, count // 4)]


def decimation_for(window: tuple[int, int, int, int], max_pixels: float = 60e6, min_factor: int = 1) -> int:
    """Integer block-average factor so a crop stays under `max_pixels` (a 100k-line OHRC strip is >1 Gpx)."""
    r0, r1, c0, c1 = window
    return max(int(min_factor), int(np.ceil(np.sqrt(max((r1 - r0) * (c1 - c0) / max_pixels, 1.0)))))


def crop_source_to_aoi(
    label_path: str | Path,
    grid_csv_path: str | Path,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    margin_px: int = 200,
    decimation: int | str = 1,
    band_range_nm: tuple[float, float] | None = None,
    rows: tuple[int, int] | None = None,
    min_decimation: int = 1,
    destripe: bool = False,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Windowed read of the source raster (opened via its PDS4 .xml label,
    since raw .img files have no self-describing header) covering the AOI.
    Returns (cropped_array, (row_start, row_stop, col_start, col_stop)) in the
    original full-strip pixel grid, for reference_window_for_source_window and
    for mapping a later match coordinate back into the full strip.

    `decimation` > 1 (or "auto") block-averages the crop on read so huge strips (OHRC, 0.26 m/px)
    fit in memory; the window stays in full-resolution pixels and `decimation_matrix` gives the
    mapping back. `destripe` removes detector-column gain stripes (push-broom IIRS). `rows` overrides the lat/lon box with an explicit line range (for polar strips whose
    lon/lat box is ill-defined). Multi-band cubes are averaged over `band_range_nm`."""
    grid = grid_csv_path if isinstance(grid_csv_path, ControlGrid) else load_geometry_grid(grid_csv_path)
    row_start, row_stop, col_start, col_stop = bbox_to_window(
        grid, lat_min, lat_max, lon_min, lon_max, margin_px
    )
    if rows is not None:
        row_start, row_stop = int(rows[0]), int(rows[1])
        col_start, col_stop = 0, int(grid.samples.max()) + 1

    with rasterio.open(label_path) as ds:
        row_stop = min(row_stop, ds.height)
        col_stop = min(col_stop, ds.width)
        window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
        win_tuple = (row_start, row_stop, col_start, col_stop)
        d = decimation_for(win_tuple, min_factor=min_decimation) if decimation == "auto" else int(decimation)
        out_hw = (int(np.ceil(window.height / d)), int(np.ceil(window.width / d))) if d > 1 else None
        bands = select_bands(label_path, ds.count, band_range_nm)
        acc = None
        for chunk in (bands[i:i + 12] for i in range(0, len(bands), 12)):
            kw = {"out_shape": (len(chunk),) + out_hw, "resampling": Resampling.average} if out_hw else {}
            part = ds.read(chunk, window=window, **kw).astype(np.float32)
            s = part.sum(axis=0)
            acc = s if acc is None else acc + s
        array = acc / len(bands) if len(bands) > 1 else (acc if ds.dtypes[0] == "float32" else acc.astype(ds.dtypes[0]))

    if destripe:
        array = remove_column_stripes(array)
    return array, (row_start, row_stop, col_start, col_stop)


def remove_column_stripes(img: np.ndarray, trend_sigma: float = 12.0) -> np.ndarray:
    """Divide out per-column gain stripes of a push-broom image: the column median profile minus its own
    smooth trend (broad cross-track brightness changes are real terrain, one-pixel-wide stripes are the
    detector)."""
    from scipy.ndimage import gaussian_filter1d

    a = img.astype(np.float32)
    valid = a > 0
    prof = np.array([np.median(a[:, j][valid[:, j]]) if valid[:, j].any() else 0.0 for j in range(a.shape[1])])
    trend = gaussian_filter1d(prof, trend_sigma, mode="nearest")
    gain = np.where((prof > 0) & (trend > 0), trend / np.maximum(prof, 1e-6), 1.0)
    return a * gain[None, :].astype(np.float32)


def decimation_matrix(window: tuple[int, int, int, int], array_shape: tuple[int, int]) -> np.ndarray:
    """3x3 matrix taking pixel coords of a (possibly decimated) crop to full-resolution crop coords."""
    r0, r1, c0, c1 = window
    fy, fx = (r1 - r0) / array_shape[0], (c1 - c0) / array_shape[1]
    return np.array([[fx, 0, 0.5 * fx - 0.5], [0, fy, 0.5 * fy - 0.5], [0, 0, 1.0]])


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
    products (e.g. a LROC NAC ROI mosaic)
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
    wrapped convention is
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


def control_grid_prior_homography(
    grid: ControlGrid,
    source_window: tuple[int, int, int, int],
    reference_transform,
    reference_crs,
    max_points: int = 2000,
) -> np.ndarray | None:
    """Independent estimate of the source-crop -> reference-raster mapping,
    straight from the same control grid used for cropping: every grid point
    inside `source_window` knows its (line, sample) and its lat/lon, so
    projecting the lat/lon into the reference raster gives a (crop-native
    source xy -> absolute reference pixel xy) correspondence set, fit by
    plain least squares. Only as accurate as the product's uncorrected
    pointing (a few hundred metres on a good product), so it is not ground
    truth -- but it is *independent of the image matching*, which makes it
    a strong sanity check on a matcher-derived fit: a real registration
    lands near it (tens of px), a wrong one lands thousands of px away."""
    import cv2

    row_start, row_stop, col_start, col_stop = source_window
    inside = (
        (grid.lines >= row_start) & (grid.lines < row_stop) & (grid.samples >= col_start) & (grid.samples < col_stop)
    )
    idx = np.flatnonzero(inside)
    if len(idx) < 4:
        return None
    if len(idx) > max_points:
        idx = idx[:: int(np.ceil(len(idx) / max_points))]

    transformer = pyproj.Transformer.from_crs(_MOON_GEOGRAPHIC, reference_crs, always_xy=True)
    anchor_x, anchor_y = reference_transform.c, reference_transform.f
    src, dst = [], []
    for i in idx:
        x, y = _project_wrap_safe(
            transformer, reference_crs, grid.lons[i], grid.lats[i], anchor_x, anchor_y
        )
        ref_row, ref_col = rowcol(reference_transform, x, y)
        src.append((grid.samples[i] - col_start, grid.lines[i] - row_start))
        dst.append((ref_col, ref_row))

    homography, _ = cv2.findHomography(np.array(src, np.float32), np.array(dst, np.float32), 0)
    return homography


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
