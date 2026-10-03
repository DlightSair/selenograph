"""Real-data accuracy checks that need no ground truth: two *independent* routes to the same answer.

  reference   the same source strip registered against two different reference mosaics
              (e.g. LRO WAC 100 m vs Chang'e-2 7 m): the two fitted mappings must put every source
              pixel in (nearly) the same place on the Moon. Their disagreement, in metres, bounds
              the combined error of both references and both fits.

  prior       the same project registered from deliberately wrong starting guesses (shifted by up to
              several km, rotated, mis-scaled): every start should converge to the same mapping as the
              unperturbed run.

    python scripts/cross_check.py reference strip_n77e200 strip_n77e200_ce2 [--runs DIR]
    python scripts/cross_check.py prior strip_n45e10 [--shifts-km 1 3 6] [--rot 3 6] [--scale 0.05 0.1]

Both write data/results/cross_checks/<name>.json and print a table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pyproj
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from algo.api._crops import load_aoi_context  # noqa: E402
from algo.geometry.nonrigid import NonRigidModel  # noqa: E402
from algo.geometry.parallax import expected_view_tangents  # noqa: E402
from algo.matching.prior_guided import RefLayer, SourcePyramid  # noqa: E402
from algo.registration import register  # noqa: E402
from algo.utils.io import MOON_RADIUS_M  # noqa: E402

OUT = ROOT.parent / "data" / "results" / "cross_checks"
GEO = pyproj.CRS.from_proj4(f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} +no_defs")


def _load(name: str):
    import os

    os.chdir(ROOT)
    cfg = yaml.safe_load((ROOT / "configs" / f"{name}.yaml").read_text())
    return cfg, load_aoi_context(cfg, decimation="auto", with_relit=True, with_dem=True)


def _register(cfg, ctx, prior):
    layers = [RefLayer(ctx.reference_crop)] + ([RefLayer(ctx.relit)] if ctx.relit is not None else [])
    return register(SourcePyramid(ctx.source_crop, ctx.source_to_full), layers if len(layers) > 1 else ctx.reference_crop, prior,
                    ctx.reference_meta.gsd, cfg.get("registration", {}), dem=ctx.dem,
                    expected_view=expected_view_tangents(ctx.source_meta) if ctx.source_meta else None)


def _footprint_points(ctx, n=20):
    full_w = ctx.source_crop.shape[1] * ctx.source_to_full[0, 0]
    full_h = ctx.source_crop.shape[0] * ctx.source_to_full[1, 1]
    gx, gy = np.meshgrid(np.linspace(0.08 * full_w, 0.92 * full_w, n), np.linspace(0.08 * full_h, 0.92 * full_h, n))
    return np.stack([gx.ravel(), gy.ravel()], axis=1)


def _to_lonlat(ctx, local_xy):
    px = local_xy + np.array([ctx.reference_col_offset, ctx.reference_row_offset]) + 0.5
    x = ctx.reference_transform.c + ctx.reference_transform.a * px[:, 0] + ctx.reference_transform.b * px[:, 1]
    y = ctx.reference_transform.f + ctx.reference_transform.d * px[:, 0] + ctx.reference_transform.e * px[:, 1]
    lon, lat = pyproj.Transformer.from_crs(ctx.reference_crs, GEO, always_xy=True).transform(x, y)
    return np.asarray(lon), np.asarray(lat)


def _dist_m(lon1, lat1, lon2, lat2):
    a, b = np.radians(lat1), np.radians(lat2)
    c = np.arccos(np.clip(np.sin(a) * np.sin(b) + np.cos(a) * np.cos(b) * np.cos(np.radians(lon1 - lon2)), -1, 1))
    return c * MOON_RADIUS_M


def _ground_positions(name: str):
    cfg, ctx = _load(name)
    res = _register(cfg, ctx, ctx.prior_local())
    if not res.ok:
        raise SystemExit(f"{name}: no fit ({res.info.get('failed')})")
    pts = _footprint_points(ctx)
    return ctx, res, _to_lonlat(ctx, res.model.to_reference(pts)), pts


def cmd_reference(a, b):
    ctx_a, res_a, (lon_a, lat_a), pts_a = _ground_positions(a)
    ctx_b, res_b, (lon_b, lat_b), pts_b = _ground_positions(b)
    # both configs crop the same product but possibly different line ranges: compare on the shared source points
    from algo.api._crops import AoiContext  # noqa: F401

    ra0, rb0 = ctx_a.source_window[0], ctx_b.source_window[0]
    # map B's sample points into A's crop coordinates (same product -> same line/sample, offset by window starts)
    pts_b_in_a = pts_b + np.array([ctx_b.source_window[2] - ctx_a.source_window[2], rb0 - ra0])
    # evaluate model A on B's points (clip to A's footprint), compare ground positions
    model_a = res_a.model
    ok = ((pts_b_in_a[:, 0] >= 0) & (pts_b_in_a[:, 1] >= 0) & (pts_b_in_a[:, 0] < ctx_a.source_crop.shape[1] * ctx_a.source_to_full[0, 0])
          & (pts_b_in_a[:, 1] < ctx_a.source_crop.shape[0] * ctx_a.source_to_full[1, 1]))
    if ok.sum() < 20:
        raise SystemExit("the two projects' crops barely overlap; use the same AOI box for a cross-check")
    lon_a2, lat_a2 = _to_lonlat(ctx_a, model_a.to_reference(pts_b_in_a[ok]))
    d = _dist_m(lon_a2, lat_a2, lon_b[ok], lat_b[ok])
    out = {"a": a, "b": b, "points": int(ok.sum()), "median_m": float(np.median(d)), "p90_m": float(np.percentile(d, 90)), "max_m": float(d.max()),
           "reference_a_gsd_m": ctx_a.reference_meta.gsd, "reference_b_gsd_m": ctx_b.reference_meta.gsd,
           "rmse_a_m": res_a.rmse_px * ctx_a.reference_meta.gsd, "rmse_b_m": res_b.rmse_px * ctx_b.reference_meta.gsd}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"ref_{a}__{b}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


def cmd_prior(name, shifts_km, rots, scales):
    cfg, ctx = _load(name)
    base = _register(cfg, ctx, ctx.prior_local())
    if not base.ok:
        raise SystemExit(f"{name}: baseline run has no fit ({base.info.get('failed')})")
    pts = _footprint_points(ctx)
    ref_pos = base.model.to_reference(pts)
    gsd = ctx.reference_meta.gsd
    prior0 = ctx.prior_local()
    full_w = ctx.source_crop.shape[1] * ctx.source_to_full[0, 0]
    full_h = ctx.source_crop.shape[0] * ctx.source_to_full[1, 1]
    centre = np.array([full_w / 2, full_h / 2, 1.0])
    c = (prior0 @ centre)[:2] / (prior0 @ centre)[2]
    rng = np.random.default_rng(0)
    cases = [("shift", s, 0.0, 0.0) for s in shifts_km] + [("rotation", 0.0, r, 0.0) for r in rots] + [("scale", 0.0, 0.0, sc) for sc in scales]
    cases.append(("combined", max(shifts_km), max(rots), max(scales)))
    rows = []
    for kind, s_km, rot, sc in cases:
        ang = rng.uniform(0, 2 * np.pi)
        t = np.array([[1, 0, s_km * 1000 / gsd * np.cos(ang)], [0, 1, s_km * 1000 / gsd * np.sin(ang)], [0, 0, 1.0]])
        th = np.radians(rot)
        s = 1.0 + sc
        R = np.array([[s * np.cos(th), -s * np.sin(th), 0], [s * np.sin(th), s * np.cos(th), 0], [0, 0, 1.0]])
        Tc, Tn = np.array([[1, 0, c[0]], [0, 1, c[1]], [0, 0, 1.0]]), np.array([[1, 0, -c[0]], [0, 1, -c[1]], [0, 0, 1.0]])
        bad_prior = t @ Tc @ R @ Tn @ prior0
        res = _register(cfg, ctx, bad_prior)
        if res.ok:
            err_px = np.hypot(*(res.model.to_reference(pts) - ref_pos).T)
            row = {"kind": kind, "shift_km": s_km, "rot_deg": rot, "scale_err": sc, "recovered": bool(np.sqrt(np.mean(err_px**2)) < 1.5),
                   "rms_px": float(np.sqrt(np.mean(err_px**2))), "rms_m": float(np.sqrt(np.mean(err_px**2)) * gsd), "rescue": res.info.get("rescue")}
        else:
            row = {"kind": kind, "shift_km": s_km, "rot_deg": rot, "scale_err": sc, "recovered": False, "failed": res.info.get("failed")}
        rows.append(row)
        print(row, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"prior_{name}.json").write_text(json.dumps({"project": name, "reference_gsd_m": gsd, "cases": rows}, indent=1, default=str))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reference")
    r.add_argument("a")
    r.add_argument("b")
    p = sub.add_parser("prior")
    p.add_argument("name")
    p.add_argument("--shifts-km", nargs="+", type=float, default=[1.0, 3.0, 6.0])
    p.add_argument("--rot", nargs="+", type=float, default=[3.0, 6.0])
    p.add_argument("--scale", nargs="+", type=float, default=[0.05, 0.1])
    args = ap.parse_args()
    if args.cmd == "reference":
        cmd_reference(args.a, args.b)
    else:
        cmd_prior(args.name, args.shifts_km, args.rot, args.scale)


if __name__ == "__main__":
    main()
