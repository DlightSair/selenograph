"""Stage 0 — parse metadata for the source (Chandrayaan-2 PDS4 label) and
reference (georeferenced raster) rasters: sun angle, GSD, footprint. Used to
seed Stage 2's coarse-to-fine search with an expected scale ratio and rotation,
not to establish ground truth (the label's own corner coordinates are exactly
the positional error the pipeline is registering out)."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from algo.utils.io import MOON_RADIUS_M, find_pds4_product, pixel_size_m
import rasterio

_NS = {
    "pds": "http://pds.nasa.gov/pds4/pds/v1",
    "isda": "https://isda.issdc.gov.in/pds4/isda/v1",
}

# Preferred first: least-corrected first for System/Refined/Corrected blocks, but we
# want the BEST available geometry for a search-window estimate, so try most-refined first.
_CORNER_BLOCKS = ("Corrected_Corner_Coordinates", "Refined_Corner_Coordinates", "System_Level_Coordinates")
_CORNER_ORDER = ("upper_left", "upper_right", "lower_right", "lower_left")


@dataclass
class ImageMetadata:
    sun_azimuth: float | None
    sun_elevation: float | None
    gsd: float | None  # metres/pixel estimate
    footprint: list[tuple[float, float]] | None  # [(lat, lon), ...] corners, UL/UR/LR/LL
    shape: tuple[int, int] | None  # (lines, samples)


def parse_pds4_label(label_path: str | Path) -> ImageMetadata:
    """Parse an ISRO ISDA PDS4 label (.xml), shared by OHRC/TMC-2/IIRS/DTM products."""
    root = ET.parse(label_path).getroot()

    params = root.find(".//isda:Product_Parameters", _NS)
    sun_azimuth = _find_float(params, "isda:sun_azimuth")
    sun_elevation = _find_float(params, "isda:sun_elevation")

    footprint = None
    for block_name in _CORNER_BLOCKS:
        block = root.find(f".//isda:{block_name}", _NS)
        if block is not None:
            footprint = _parse_corners(block)
            break

    shape = _parse_shape(root)
    gsd = _estimate_gsd(footprint, shape) if footprint and shape else None

    return ImageMetadata(sun_azimuth, sun_elevation, gsd, footprint, shape)


def load_reference_metadata(raster_path: str | Path) -> ImageMetadata:
    """Derive reference-image metadata from a georeferenced raster (no PDS label)."""
    with rasterio.open(raster_path) as ds:
        bounds, transform, crs = ds.bounds, ds.transform, ds.crs
        shape = (ds.height, ds.width)
    footprint = [
        (bounds.top, bounds.left),
        (bounds.top, bounds.right),
        (bounds.bottom, bounds.right),
        (bounds.bottom, bounds.left),
    ]
    dx, _dy = pixel_size_m(transform, crs)
    return ImageMetadata(sun_azimuth=None, sun_elevation=None, gsd=dx, footprint=footprint, shape=shape)


def load_metadata(source_cfg: dict, reference_cfg: dict) -> tuple[ImageMetadata, ImageMetadata]:
    """source_cfg['path'] is a PDS4 product directory; reference_cfg['path'] is a
    georeferenced raster (e.g. a QuickMap PNG+VRT export)."""
    _data_path, label_path = find_pds4_product(source_cfg["path"])
    source_meta = parse_pds4_label(label_path)
    reference_meta = load_reference_metadata(reference_cfg["path"])
    return source_meta, reference_meta


def _find_float(parent, tag: str) -> float | None:
    if parent is None:
        return None
    el = parent.find(tag, _NS)
    return float(el.text) if el is not None and el.text else None


def _parse_corners(block) -> list[tuple[float, float]]:
    corners = []
    for prefix in _CORNER_ORDER:
        lat = block.find(f"isda:{prefix}_latitude", _NS)
        lon = block.find(f"isda:{prefix}_longitude", _NS)
        if lat is not None and lon is not None:
            corners.append((float(lat.text), float(lon.text)))
    return corners


def _parse_shape(root) -> tuple[int, int] | None:
    dims = {}
    for axis in root.findall(".//pds:Axis_Array", _NS):
        name = axis.find("pds:axis_name", _NS)
        elements = axis.find("pds:elements", _NS)
        if name is not None and elements is not None:
            dims[name.text] = int(elements.text)
    if "Line" in dims and "Sample" in dims:
        return (dims["Line"], dims["Sample"])
    return None


def _estimate_gsd(footprint, shape) -> float | None:
    """Across-track GSD in metres/pixel from the upper-left/upper-right corner
    separation and sample count (great-circle distance on a spherical Moon)."""
    (lat1, lon1), (lat2, lon2) = footprint[0], footprint[1]
    lat_m = math.radians((lat1 + lat2) / 2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    distance_m = MOON_RADIUS_M * math.hypot(dlat, dlon * math.cos(lat_m))
    samples = shape[1]
    return distance_m / samples if samples else None
