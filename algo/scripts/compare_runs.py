"""Compare two *finished* runs of the same source strip, in metres on the Moon.

    python scripts/compare_runs.py <run_id_A> <run_id_B>

Each run's transform.json (homography + non-rigid field, in its own reference raster's pixel frame) maps the source
crop to the reference raster; both are converted to lon/lat through their own reference georeferencing and compared
over a lattice of source pixels. Useful for: the same strip against two independent references (LRO WAC vs
Chang'e-2), with and without the re-lit DEM layer, before/after a code change. The two runs must cover the same
source rows (same product and `source_rows`/AOI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pyproj
import rasterio
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from algo.geometry.nonrigid import NonRigidModel  # noqa: E402
from algo.utils.io import MOON_RADIUS_M  # noqa: E402

RESULTS = ROOT.parent / "data" / "results"
GEO = pyproj.CRS.from_proj4(f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")


def load(run_id: str):
    run = RESULTS / run_id
    meta = json.loads((run / "meta.json").read_text())
    cfg = yaml.safe_load((ROOT / "configs" / meta["config"]).read_text())
    tj = json.loads((run / "transform.json").read_text())
    off = tj["reference_offset"]
    H_abs = np.array(tj["homography"], dtype=np.float64)
    T = np.array([[1, 0, -off["col"]], [0, 1, -off["row"]], [0, 0, 1.0]])
    nr = tj.get("nonrigid") or {}
    model_local = NonRigidModel.from_dict({"homography": (T @ H_abs).tolist(), "field": nr.get("field"), "info": nr.get("info", {})})
    with rasterio.open(ROOT / cfg["reference"]["path"]) as ds:
        transform, crs = ds.transform, ds.crs
    to_geo = pyproj.Transformer.from_crs(crs, GEO, always_xy=True)

    def lonlat(src_xy: np.ndarray):
        p = model_local.to_reference(src_xy) + np.array([off["col"], off["row"]]) + 0.5
        x = transform.c + transform.a * p[:, 0] + transform.b * p[:, 1]
        y = transform.f + transform.d * p[:, 0] + transform.e * p[:, 1]
        lon, lat = to_geo.transform(x, y)
        return np.asarray(lon), np.asarray(lat)

    return meta, cfg, tj, lonlat


def main() -> None:
    a_id, b_id = sys.argv[1:3]
    meta_a, cfg_a, tj_a, ll_a = load(a_id)
    meta_b, cfg_b, tj_b, ll_b = load(b_id)
    # source sizes from the homography's own domain are unknown here; sample the central 80% of a typical strip crop
    # taken from the cropped metrics (matches.csv extent of run A)
    import csv

    pts = np.array([[float(r["source_x"]), float(r["source_y"])] for r in csv.DictReader(open(RESULTS / a_id / "matches.csv"))])
    lo, hi = np.percentile(pts, 2, axis=0), np.percentile(pts, 98, axis=0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 25), np.linspace(lo[1], hi[1], 40))
    grid = np.stack([gx.ravel(), gy.ravel()], axis=1)
    lon_a, lat_a = ll_a(grid)
    lon_b, lat_b = ll_b(grid)
    a, b = np.radians(lat_a), np.radians(lat_b)
    d = np.arccos(np.clip(np.sin(a) * np.sin(b) + np.cos(a) * np.cos(b) * np.cos(np.radians(lon_a - lon_b)), -1, 1)) * MOON_RADIUS_M
    out = {"a": {"run": a_id, "config": meta_a["config"]}, "b": {"run": b_id, "config": meta_b["config"]}, "points": len(d),
           "median_m": float(np.median(d)), "p90_m": float(np.percentile(d, 90)), "max_m": float(d.max())}
    print(json.dumps(out, indent=1))
    (RESULTS / "cross_checks").mkdir(parents=True, exist_ok=True)
    (RESULTS / "cross_checks" / f"compare_{meta_a['config'][:-5]}__{meta_b['config'][:-5]}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
