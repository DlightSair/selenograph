"""Draw a CH2 product's control-grid footprint outline on a reference GeoTIFF (any CRS) and
save a downsampled PNG, so a reference can be eyeballed before it is used.

    python scripts/check_reference_footprint.py --product <product dir> --reference <ref.tif> [--out PNG]

The outline is the first/last sample column and first/last line of the product's
geometry/*_g_grd_*.csv, projected into the reference CRS exactly like the pipeline does
(longitudes 0..360 are fine: pyproj normalises them). Also prints how much of the footprint
lies inside the raster and what fraction of the raster is valid (non-zero).
    -> data/raw/lro_reference/_checks/<reference stem>_footprint.png  (default)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pyproj
import rasterio

sys.path.insert(0, str(Path(__file__).parent))
from fetch_trek_polar_nac import find_grid_csv, load_grid  # noqa: E402

CHECKS = Path(__file__).parents[2] / "data" / "raw" / "lro_reference" / "_checks"
MOON = pyproj.CRS.from_proj4("+proj=longlat +R=1737400 +no_defs")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--product", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    lon, lat, pix, scan = load_grid(find_grid_csv(a.product))
    with rasterio.open(a.reference) as ds:
        img, T, crs = ds.read(1), ds.transform, ds.crs
    to_ref = pyproj.Transformer.from_crs(MOON, crs, always_xy=True)
    x, y = to_ref.transform(lon, lat)
    col, row = (x - T.c) / T.a, (y - T.f) / T.e
    inside = (col >= 0) & (col < img.shape[1]) & (row >= 0) & (row < img.shape[0])
    print(f"{100 * inside.mean():.1f}% of control points inside the raster; "
          f"{100 * (img > 0).mean():.1f}% of the raster is non-zero")

    left = np.flatnonzero(pix == pix.min()); left = left[np.argsort(scan[left])]
    right = np.flatnonzero(pix == pix.max()); right = right[np.argsort(-scan[right])]
    idx = np.concatenate([left, right])
    sc = min(1.0, 1600 / max(img.shape))
    lo, hi = np.percentile(img[img > 0], (1, 99)) if (img > 0).any() else (0, 255)
    g = np.clip((img.astype(np.float32) - lo) / (hi - lo + 1e-6) * 255, 0, 255).astype(np.uint8)
    vis = cv2.cvtColor(cv2.resize(g, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    pts = np.stack([col[idx] * sc, row[idx] * sc], 1).astype(np.int32)
    cv2.polylines(vis, [pts], True, (0, 0, 255), 2)
    out = Path(a.out) if a.out else CHECKS / f"{Path(a.reference).stem}_footprint.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), vis)
    print(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
