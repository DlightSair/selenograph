"""Write a project config for a Chandrayaan-2 product from its own control grid.

    python scripts/make_config.py <name> <product dir> <reference tif> [--rows R0 R1] [--dem DEM.tif] [--relit]
           [--provider P] [--layer L] [--band-range 900 1600] [--note "..."]

The AOI lat/lon box is the footprint of the chosen line range, taken from the control grid (or from the
label corners for RAW products), so it works for polar strips where a hand-written box is awkward.
`--rows` restricts a long strip to a stretch (e.g. the lit part of an OHRC pass); `--relit` turns on the
illumination-aware layer (the DEM re-lit with the source's own Sun) and, with a DEM, the parallax model.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from algo.api._crops import find_source_label_and_grid  # noqa: E402
from algo.preprocessing.grid import load_geometry_grid  # noqa: E402
from algo.preprocessing.metadata import parse_pds4_label  # noqa: E402


def rel(path: str | Path) -> str:
    return Path(__import__("os").path.relpath(Path(path).resolve(), ROOT)).as_posix()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("product")
    ap.add_argument("reference")
    ap.add_argument("--rows", nargs=2, type=int)
    ap.add_argument("--dem")
    ap.add_argument("--relit", action="store_true")
    ap.add_argument("--provider", default="lroc_nac_mosaic")
    ap.add_argument("--layer", default="")
    ap.add_argument("--band-range", nargs=2, type=float)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    label, grid_src = find_source_label_and_grid({"path": args.product})
    from algo.preprocessing.grid import ControlGrid

    grid = grid_src if isinstance(grid_src, ControlGrid) else load_geometry_grid(grid_src)
    meta = parse_pds4_label(label)
    sel = np.ones(len(grid.lines), bool)
    if args.rows:
        sel = (grid.lines >= args.rows[0]) & (grid.lines <= args.rows[1])
    lats, lons = grid.lats[sel], grid.lons[sel]
    # longitudes are 0..360; a strip that straddles 0 would need a wrapped box, which the AOI box cannot express
    lon_min, lon_max = float(lons.min()), float(lons.max())
    if lon_max - lon_min > 180:
        print("warning: footprint straddles lon 0/360 or the pole; the lat/lon box is the whole strip -- rely on source_rows", file=sys.stderr)
    aoi = {"name": args.name, "lat_min": round(float(lats.min()), 3), "lat_max": round(float(lats.max()), 3),
           "lon_min": round(lon_min, 3), "lon_max": round(lon_max, 3)}
    if args.rows:
        aoi["source_rows"] = list(args.rows)
    instrument = {"ohr": "OHRC", "tmc": "TMC2", "iir": "IIRS"}.get(Path(args.product).name.split("_")[1], "TMC2")
    source = {"instrument": instrument, "product_type": "calibrated", "path": rel(args.product)}
    if args.band_range:
        source["band_range_nm"] = list(args.band_range)
    cfg = {
        "aoi": aoi,
        "source": source,
        "reference": {"provider": args.provider, "layer": args.layer or Path(args.reference).stem, "path": rel(args.reference)},
        "dem": {"enabled": bool(args.dem), **({"path": rel(args.dem)} if args.dem else {})},
        "pyramid": {"levels": 4, "downsample_factor": 4},
        "matching": {"primary": "loftr", "fallback": "classical", "confidence_threshold": 0.5,
                     "crater": {"num_peaks": 40, "min_distance": 8, "smooth_sigma": 2, "ratio_test": 0.75}},
        "anms": {"grid_size": 8, "max_matches_per_tile": 25},
        "geometry": {"transform": "homography", "ransac": "magsac", "reproj_threshold_px": 3.0},
        "evaluation": {"output_dir": "../data/results/"},
    }
    if args.relit and args.dem:
        cfg["registration"] = {"mode": "prior_guided", "relit": {"enabled": True, "dem": rel(args.dem), "weight": 1.0}}
    out = ROOT / "configs" / f"{args.name}.yaml"
    header = "".join(f"# {line}\n" for line in args.note.splitlines()) if args.note else ""
    sun = f"sun az/el {meta.sun_azimuth:.0f}/{meta.sun_elevation:.1f} deg" if meta.sun_azimuth is not None else ""
    header += f"# {instrument} {Path(args.product).name}: {meta.gsd} m/px, {sun}, roll/pitch {meta.roll}/{meta.pitch} deg\n"
    out.write_text(header + yaml.safe_dump(cfg, sort_keys=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
