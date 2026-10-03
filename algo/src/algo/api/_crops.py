"""Shared AOI crop-loading used by the pipeline, overlay.py, preview.py and visualization.py
-- one place, so they cannot silently diverge on how a crop, its decimation, the control-grid
prior or the DEM-relit reference layer are produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import rasterio

from algo.preprocessing.grid import (
    ControlGrid,
    control_grid_prior_homography,
    corner_control_grid,
    crop_reference_to_window,
    crop_source_to_aoi,
    decimation_matrix,
    load_geometry_grid,
    reference_window_for_source_window,
)
from algo.preprocessing.metadata import ImageMetadata, load_metadata
from algo.utils.io import find_pds4_product


def find_source_label_and_grid(source_cfg: dict):
    """(label, grid): `grid` is the product's control-grid CSV, or a synthetic `ControlGrid` built from the
    label's corner coordinates when the product ships none (RAW level)."""
    from pathlib import Path

    product_dir = Path(source_cfg["path"])
    _data_path, label_path = find_pds4_product(product_dir)
    csv = next((product_dir / "geometry").rglob("*.csv"), None) if (product_dir / "geometry").exists() else None
    return label_path, (csv if csv is not None else corner_control_grid(label_path))


@dataclass
class AoiContext:
    source_crop: np.ndarray  # possibly decimated (block-averaged) -- see source_to_full
    reference_crop: np.ndarray
    reference_row_offset: int
    reference_col_offset: int
    source_window: tuple[int, int, int, int]  # full-resolution (row_start, row_stop, col_start, col_stop)
    grid: ControlGrid
    reference_transform: object
    reference_crs: object
    source_to_full: np.ndarray = field(default_factory=lambda: np.eye(3))  # source_crop px -> full-res crop px
    source_meta: ImageMetadata | None = None
    reference_meta: ImageMetadata | None = None
    grid_is_synthetic: bool = False
    relit: np.ndarray | None = None  # DEM lit by the source's Sun, on the reference crop grid
    dem: np.ndarray | None = None  # DEM heights (m) on the reference crop grid, NaN where unknown

    @property
    def decimation(self) -> float:
        return float(self.source_to_full[0, 0])

    @property
    def reference_window(self) -> tuple[int, int, int, int]:
        h, w = self.reference_crop.shape
        return (self.reference_row_offset, self.reference_row_offset + h, self.reference_col_offset, self.reference_col_offset + w)

    def prior_local(self) -> np.ndarray | None:
        """Control-grid prior: full-resolution source crop px -> reference-crop-local px."""
        H = control_grid_prior_homography(self.grid, self.source_window, self.reference_transform, self.reference_crs)
        if H is None:
            return None
        to_local = np.array([[1, 0, -self.reference_col_offset], [0, 1, -self.reference_row_offset], [0, 0, 1]], dtype=np.float64)
        return to_local @ H


def load_aoi_context(config: dict, decimation: int | str = "auto", with_relit: bool = False, with_dem: bool = False) -> AoiContext:
    """`decimation="auto"` block-averages huge source crops on read (an OHRC strip is >1 Gpx) to roughly
    the reference's resolution; pass 1 for the full-resolution crop."""
    label_path, grid_csv = find_source_label_and_grid(config["source"])
    aoi = config["aoi"]
    try:
        source_meta, reference_meta = load_metadata(config["source"], config["reference"])
    except Exception:  # noqa: BLE001 -- metadata is only used to pick a decimation and the Sun for relighting
        source_meta = reference_meta = None
    min_dec = 1
    if source_meta and reference_meta and source_meta.gsd and reference_meta.gsd:
        ratio = reference_meta.gsd / source_meta.gsd
        min_dec = max(1, int(0.5 * ratio)) if ratio >= 2 else 1  # matcher reduces to the reference scale anyway
    source_crop, source_window = crop_source_to_aoi(
        label_path, grid_csv, aoi["lat_min"], aoi["lat_max"], aoi["lon_min"], aoi["lon_max"],
        decimation=decimation, band_range_nm=config["source"].get("band_range_nm"),
        rows=aoi.get("source_rows"), min_decimation=min_dec,
        destripe=bool(config["source"].get("destripe", str(config["source"].get("instrument", "")).upper() == "IIRS")),
    )
    grid = grid_csv if isinstance(grid_csv, ControlGrid) else load_geometry_grid(grid_csv)
    synthetic_grid = isinstance(grid_csv, ControlGrid)  # label-corner geolocation: km-scale error, widen the window
    with rasterio.open(config["reference"]["path"]) as ds:
        reference_transform, reference_crs = ds.transform, ds.crs
    ref_gsd_m = reference_meta.gsd if reference_meta and reference_meta.gsd else 5.0
    reference_window = reference_window_for_source_window(
        grid, source_window, reference_transform, reference_crs,
        margin_px=int(max(20, (4000.0 if synthetic_grid else 1500.0) / ref_gsd_m)),  # the prior can be km off; keep the truth inside the crop
    )
    reference_crop = crop_reference_to_window(config["reference"]["path"], reference_window)

    ctx = AoiContext(
        source_crop, reference_crop, int(reference_window[0]), int(reference_window[2]),
        source_window, grid, reference_transform, reference_crs,
        source_to_full=decimation_matrix(source_window, source_crop.shape),
        source_meta=source_meta, reference_meta=reference_meta, grid_is_synthetic=synthetic_grid,
    )
    if with_relit:
        ctx.relit = load_relit_layer(config, ctx)
    if with_dem:
        ctx.dem = load_dem_heights(config, ctx)
    return ctx


def _dem_path(config: dict) -> str | None:
    reg = config.get("registration", {})
    return (reg.get("relit") or {}).get("dem") or reg.get("dem") or (
        config.get("dem", {}).get("path") if config.get("dem", {}).get("enabled") else None
    )


def load_dem_heights(config: dict, ctx: AoiContext) -> np.ndarray | None:
    """DEM heights on the reference crop grid, for the parallax model (None without a usable DEM)."""
    path = _dem_path(config)
    if not path or not config.get("registration", {}).get("parallax", True):
        return None
    from algo.illumination.dem import dem_on_reference_grid

    dem = dem_on_reference_grid(path, ctx.reference_transform, ctx.reference_crs, ctx.reference_window, 0)
    return dem if np.isfinite(dem).mean() > 0.3 else None


def load_relit_layer(config: dict, ctx: AoiContext) -> np.ndarray | None:
    """The configured DEM lit with the source's own Sun, on the reference crop grid (None if no DEM
    is configured, the Sun is unknown, or the DEM does not cover the crop)."""
    reg = config.get("registration", {})
    relit_cfg = reg.get("relit") or {}
    dem_path = _dem_path(config)
    meta = ctx.source_meta
    if not relit_cfg.get("enabled", False) or not dem_path or not meta or meta.sun_azimuth is None or meta.sun_elevation is None:
        return None
    from algo.illumination.dem import relit_reference

    return relit_reference(dem_path, ctx.reference_transform, ctx.reference_crs, ctx.reference_window,
                           meta.sun_azimuth, meta.sun_elevation)
