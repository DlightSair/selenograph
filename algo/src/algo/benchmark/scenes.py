"""Benchmark scenes built from the real Tycho data already in the repo: the 5 m LROC NAC mosaic
(real albedo + shading) and the TMC-2 DTM resampled onto its grid (real relief)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import rasterio

from algo.benchmark import synth
from algo.illumination.relight import render_dem

REPO = Path(__file__).resolve().parents[4]
NAC_PATH = REPO / "data" / "raw" / "lro_reference" / "tycho" / "nac" / "NAC_ROI_TYCHOCTRLOA_E430S3489_5M.TIF"
DEM_PATH = REPO / "data" / "dem" / "tycho" / "dem_on_nac_grid.tif"
PIXEL_M = 5.0


@dataclass
class TychoScene:
    nac: np.ndarray  # uint8
    dem: np.ndarray  # float32 metres, NaN where missing
    valid_integral: np.ndarray  # integral image of (DEM and NAC valid)
    nac_integral: np.ndarray  # integral image of (NAC valid)

    def window(self, size: int, rng: np.random.Generator, need_dem: bool = True) -> tuple[np.ndarray, np.ndarray]:
        h, w = self.nac.shape
        ii = self.valid_integral if need_dem else self.nac_integral
        for _ in range(2000):
            y0 = int(rng.integers(0, h - size))
            x0 = int(rng.integers(0, w - size))
            frac = (ii[y0 + size, x0 + size] - ii[y0, x0 + size] - ii[y0 + size, x0] + ii[y0, x0]) / (size * size)
            if frac > (0.995 if need_dem else 0.95):  # NAC-only scenes tolerate the mosaic's few no-data corners
                return self.nac[y0:y0 + size, x0:x0 + size].astype(np.float32), self.dem[y0:y0 + size, x0:x0 + size].astype(np.float32)
        raise RuntimeError("no fully valid DEM window of that size")


COPERNICUS_NAC = REPO / "data" / "raw" / "lro_reference" / "copernicus" / "nac" / "NAC_ROI_COPERNICLOB_E103N3402_5M.TIF"


@lru_cache(maxsize=2)
def tycho_scene(name: str = "tycho") -> TychoScene:
    """`tycho`: NAC mosaic + TMC DTM (both illumination and geometry scenes). `copernicus`: NAC mosaic only and larger
    (7300 x 13800 px), for the extreme scale ratios whose windows do not fit in the Tycho mosaic."""
    nac_path = NAC_PATH if name == "tycho" else COPERNICUS_NAC
    with rasterio.open(nac_path) as ds:
        nac = ds.read(1)
    if name == "tycho":
        with rasterio.open(DEM_PATH) as ds:
            dem = ds.read(1).astype(np.float32)
        dem[dem < -30000] = np.nan
    else:
        dem = np.full(nac.shape, np.nan, np.float32)

    def integral(mask):
        return np.pad(np.cumsum(np.cumsum(mask, axis=0, dtype=np.int32), axis=1, dtype=np.int32), ((1, 0), (1, 0)))

    return TychoScene(nac, dem, integral(np.isfinite(dem) & (nac > 0)), integral(nac > 0))


@dataclass
class Spec:
    """One benchmark case. Every field has a neutral default, so a sweep just overrides one or two."""

    content: str = "nac"  # "nac": real NAC image as terrain; "dem": DEM rendered at two Suns
    seed: int = 0
    src_size: int = 800  # source frame side, source px
    k_ref: float = 1.0  # reference block-averaged by this factor (5 m source vs 100 m WAC => 20)
    k_src: float = 1.0  # base px per source px (>1: source coarser than the 5 m base)
    sun_ref: tuple[float, float] = (300.0, 25.0)  # azimuth, elevation (the NAC mosaic's own, estimated)
    sun_src: tuple[float, float] = (43.0, 39.0)
    albedo: float = 0.25
    rotation_deg: float = 0.0
    perspective: float = 0.0
    field_amp_px: float = 0.0  # smooth non-rigid field, base px RMS
    jitter_amp_px: float = 0.0
    parallax_view_deg: float = 0.0  # DEM-driven parallax along-track for this view angle
    prior_shift_px: float = 60.0  # reference px
    prior_rot_deg: float = 0.5
    prior_scale_err: float = 0.01
    noise: float = 0.02
    dem_blur_px: float = 0.0  # resolution of the DEM available to the relighter (blur, base px); real LOLA is coarser than the imagery
    scene: str = "tycho"  # which real mosaic supplies the terrain
    label: str = ""


def build_pair(spec: Spec) -> tuple[synth.Pair, tuple[int, int]]:
    scene = tycho_scene(spec.scene)
    rng = np.random.default_rng(spec.seed)
    s = spec.k_src
    # base window big enough to hold the rotated source footprint plus the search margin
    margin = int(spec.k_ref * (2.2 * spec.prior_shift_px + 60) + 150)
    size = int(min(min(scene.nac.shape) - 2, spec.src_size * s * 1.42 + 2 * margin))
    nac, dem = scene.window(size, rng, need_dem=(spec.content == "dem" or spec.parallax_view_deg > 0))
    if spec.content == "dem":
        albedo = synth.fractal_albedo(dem.shape, rng, spec.albedo)
        base_ref = synth.to_u8(render_dem(dem, PIXEL_M, *spec.sun_ref) * albedo) + 1.0
        base_src = synth.to_u8(render_dem(dem, PIXEL_M, *spec.sun_src) * albedo) + 1.0
    else:
        base_ref = nac + 1.0
        base_src = nac + 1.0

    src_shape = (spec.src_size, spec.src_size)
    truth = synth.make_geometry(
        src_shape, base_ref.shape, scale=s, rotation_deg=spec.rotation_deg, perspective=spec.perspective,
        field_amp_px=spec.field_amp_px, jitter_amp_px=spec.jitter_amp_px, rng=rng,
    )
    if spec.parallax_view_deg:
        h0 = np.nan_to_num(dem - np.nanmedian(dem))
        truth.dem_parallax = (h0.astype(np.float32), float(np.tan(np.radians(spec.parallax_view_deg)) / PIXEL_M))
        truth.dem_dir = (0.0, 1.0)  # fore/aft look is along the track (rows)
    source, _ = synth.render_source(base_src, truth, src_shape, s, rng, noise=spec.noise,
                                    gain=float(rng.uniform(0.6, 1.5)), gamma=float(rng.uniform(0.85, 1.2)))
    reference = synth.downsample(base_ref, spec.k_ref)
    D = synth.base_to_ref_matrix(spec.k_ref, reference.shape, base_ref.shape)

    def truth_ref(pts):
        return synth.apply_h(D, truth.to_base(pts))

    H_true_ref = D @ truth.H
    H_prior = synth.perturb_prior(H_true_ref, src_shape, spec.prior_shift_px, spec.prior_rot_deg, spec.prior_scale_err, rng)
    meta = {"label": spec.label}
    if spec.parallax_view_deg > 0 or spec.content == "dem":
        # the DEM a pipeline would have: coarser than the imagery, on the reference grid
        dem_avail0 = np.nan_to_num(dem, nan=float(np.nanmedian(dem)))
        if spec.dem_blur_px > 0:
            dem_avail0 = cv2.GaussianBlur(dem_avail0, (0, 0), spec.dem_blur_px)
        meta["dem_ref"] = synth.downsample(dem_avail0, spec.k_ref)
    if spec.content == "dem":
        # what a real pipeline could build: the (coarser, albedo-free) DEM lit with the *source's* own Sun
        dem_avail = cv2.GaussianBlur(np.nan_to_num(dem), (0, 0), spec.dem_blur_px) if spec.dem_blur_px > 0 else dem
        relit = synth.to_u8(render_dem(dem_avail, PIXEL_M, *spec.sun_src)) + 1.0
        meta["relit"] = synth.downsample(relit, spec.k_ref)
    if spec.parallax_view_deg > 0:
        meta["expected_view"] = (float(np.tan(np.radians(spec.parallax_view_deg))), 0.0)  # what the label's pitch/camera tilt gives
    pair = synth.Pair(source, reference, PIXEL_M * spec.k_ref, H_prior, truth_ref, meta=meta)
    return pair, src_shape
