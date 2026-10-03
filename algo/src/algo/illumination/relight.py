"""Physically-based re-lighting of a DEM: the illumination-variation answer.

Registration between two images of the same terrain taken under different Sun
angles is hard because the *appearance* changes -- shading flips polarity,
shadows move, albedo contrast is swamped by topographic shading. At low Sun
(polar OHRC strips are imaged at 1-4 degrees elevation) the picture is almost
pure topography. A DEM, on the other hand, does not depend on illumination at
all. So instead of hoping that some image descriptor is invariant to the Sun,
render the DEM with the *source image's own* Sun azimuth/elevation and register
against that. Shading, terminator position and cast-shadow edges then line up
with the source by construction.

Model: a lunar-Lambert photometric function (Lommel-Seeliger blended with
Lambert), per-pixel incidence/emission angle from the DEM slopes, and hard cast
shadows by a horizon scan along the Sun azimuth. Albedo is taken as constant
unless an albedo map is supplied.

Conventions
-----------
* `dem` is a north-up raster (row 0 = north), heights in metres, square pixels of
  `pixel_m` metres.
* Azimuth is compass degrees clockwise from north *toward the Sun* (the PDS4
  `sun_azimuth` of Chandrayaan-2 labels); elevation is degrees above the horizon.
* Nadir viewing (emission angle = slope) is assumed -- right for OHRC and the
  TMC-2 nadir camera, an approximation for the +-25 deg fore/aft cameras.
"""

from __future__ import annotations

import cv2
import numpy as np


def surface_normal_z_and_incidence(dem: np.ndarray, pixel_m: float, sun_az_deg: float, sun_el_deg: float):
    """Returns (cos_incidence, cos_emission) for nadir viewing, from central-difference slopes."""
    z = dem.astype(np.float32)
    dz_dx = cv2.Sobel(z, cv2.CV_32F, 1, 0, ksize=3, borderType=cv2.BORDER_REPLICATE) / (8.0 * pixel_m)
    dz_dy_rows = cv2.Sobel(z, cv2.CV_32F, 0, 1, ksize=3, borderType=cv2.BORDER_REPLICATE) / (8.0 * pixel_m)
    dz_dnorth = -dz_dy_rows  # rows run south
    inv_norm = 1.0 / np.sqrt(1.0 + dz_dx**2 + dz_dnorth**2)
    nx, ny, nz = -dz_dx * inv_norm, -dz_dnorth * inv_norm, inv_norm
    az, el = np.radians(sun_az_deg), np.radians(sun_el_deg)
    sx, sy, sz = np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)
    return nx * sx + ny * sy + nz * sz, nz


def cast_shadow_mask(dem: np.ndarray, pixel_m: float, sun_az_deg: float, sun_el_deg: float) -> np.ndarray:
    """True where terrain blocks the Sun. The DEM is rotated so the Sun lies along +x, then a
    running "shadow ceiling" is swept from the sunward edge: a pixel is shadowed when it sits
    below the ceiling cast by everything between it and the Sun."""
    if sun_el_deg <= 0:
        return np.ones(dem.shape, bool)
    h, w = dem.shape
    # rotate by the azimuth so that the direction toward the Sun becomes image +x
    diag = int(np.ceil(np.hypot(h, w)))
    centre = ((w - 1) / 2.0, (h - 1) / 2.0)
    # rotation matrix mapping the sun direction to +x: image coords (x east, y south)
    # sun direction in image coords: (sin az, -cos az); we want it at (1, 0).
    R = np.array([[np.sin(np.radians(sun_az_deg)), -np.cos(np.radians(sun_az_deg))],
                  [np.cos(np.radians(sun_az_deg)), np.sin(np.radians(sun_az_deg))]])
    # forward map p' = R (p - centre) + (diag/2, diag/2)
    M = np.zeros((2, 3))
    M[:, :2] = R
    M[:, 2] = np.array([diag / 2.0, diag / 2.0]) - R @ np.array(centre)
    big = cv2.warpAffine(dem.astype(np.float32), M, (diag, diag), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=float(np.nanmin(dem)) - 1e4)

    drop = pixel_m * np.tan(np.radians(sun_el_deg))  # ceiling falls this much per pixel away from the Sun
    shadow = np.zeros(big.shape, bool)
    ceiling = big[:, -1].copy()
    for x in range(diag - 2, -1, -1):
        ceiling = ceiling - drop
        z = big[:, x]
        shadow[:, x] = z < ceiling - 1e-3
        ceiling = np.maximum(ceiling, z)

    # warp the mask back into the original frame
    Minv = cv2.invertAffineTransform(M)
    back = cv2.warpAffine(shadow.astype(np.float32), Minv, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)
    return back > 0.5


def render_dem(
    dem: np.ndarray,
    pixel_m: float,
    sun_az_deg: float,
    sun_el_deg: float,
    *,
    albedo: np.ndarray | None = None,
    lambert_weight: float = 0.3,
    shadows: bool = True,
    ambient: float = 0.02,
    penumbra_px: float = 0.8,
) -> np.ndarray:
    """Float image in [0, ~1]: the DEM as it would look under the given Sun.

    `lambert_weight` blends Lambert (1) with Lommel-Seeliger (0): the Moon near zero phase is
    close to Lommel-Seeliger (little limb darkening), with a Lambertian part growing with phase.
    NaN heights are filled from the nearest valid value so slopes stay finite; the returned image
    has 0 where the DEM was invalid."""
    dem = np.asarray(dem, dtype=np.float32)
    invalid = ~np.isfinite(dem)
    if invalid.any():
        fill = float(np.nanmedian(dem)) if (~invalid).any() else 0.0
        dem = np.where(invalid, fill, dem)

    mu0, mu = surface_normal_z_and_incidence(dem, pixel_m, sun_az_deg, sun_el_deg)
    mu0 = np.clip(mu0, 0.0, 1.0)
    mu = np.clip(mu, 1e-3, 1.0)
    ls = 2.0 * mu0 / (mu0 + mu)
    lam = mu0
    img = (1.0 - lambert_weight) * ls + lambert_weight * lam
    if albedo is not None:
        img = img * albedo
    if shadows:
        shaded = cast_shadow_mask(dem, pixel_m, sun_az_deg, sun_el_deg)
        lit = (~shaded).astype(np.float32)
        if penumbra_px > 0:
            lit = cv2.GaussianBlur(lit, (0, 0), penumbra_px)
        img = img * lit
    img = img + ambient  # sky-free Moon: just a small floor so deep shadow keeps a defined level
    img[invalid] = 0.0
    return img.astype(np.float32)
