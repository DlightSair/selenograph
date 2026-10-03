"""Run benchmark specs against registration variants, in parallel, and summarise.

    python -m algo.benchmark.runner illumination --workers 6
"""

from __future__ import annotations

import os

os.environ.setdefault("ALGO_THREADS", "1")  # the sweep already runs one case per process

import json
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict

import numpy as np

from algo.benchmark.scenes import REPO, Spec, build_pair
from algo.benchmark.synth import apply_h, evaluate_model
from algo.matching.prior_guided import RefLayer
from algo.registration import register

OUT = REPO / "data" / "benchmark"
SUCCESS_PX = 1.5  # a case "succeeds" when its RMS error against the truth is under this many reference pixels


def run_variant(pair, src_shape, cfg: dict) -> dict:
    layers = [RefLayer(pair.reference)]
    if cfg.get("relit_weight", 0) > 0 and "relit" in pair.meta:
        layers.append(RefLayer(pair.meta["relit"], cfg["relit_weight"]))
    t0 = time.time()
    reg_cfg = {k: v for k, v in cfg.items() if k not in ("relit_weight", "use_dem")}
    dem = pair.meta.get("dem_ref") if cfg.get("use_dem") else None
    res = register(pair.source, layers if len(layers) > 1 else pair.reference, pair.H_prior, pair.reference_gsd, reg_cfg, dem=dem,
                   expected_view=pair.meta.get("expected_view") if cfg.get("use_dem") else None)
    row = {"seconds": round(time.time() - t0, 1), "matches": len(res.matches), "inliers": len(res.inliers)}
    if not res.ok:
        row.update({"ok": False, "failed": res.info.get("failed", "no fit"), "rmse_px": None})
        return row
    ev = evaluate_model(res.model.to_reference, pair, src_shape)
    row.update({"ok": ev["rmse_px"] < SUCCESS_PX, **{k: round(v, 4) for k, v in ev.items()}})
    nr = res.model.info
    row["nonrigid"] = nr.get("nonrigid")
    row["cv_gain_pct"] = nr.get("cv_gain_pct")
    if nr.get("parallax"):
        row["parallax_alpha"] = [nr["parallax"]["alpha_along"], nr["parallax"]["alpha_cross"]]
    return row


def run_case(args: tuple[Spec, dict[str, dict]]) -> list[dict]:
    spec, variants = args
    try:
        pair, src_shape = build_pair(spec)
    except Exception as exc:  # noqa: BLE001
        return [{**asdict(spec), "variant": "build", "ok": False, "failed": f"build: {exc}"}]
    prior = evaluate_model(lambda p: apply_h(pair.H_prior, p), pair, src_shape)
    rows = []
    for name, cfg in variants.items():
        try:
            row = run_variant(pair, src_shape, cfg)
        except Exception as exc:  # noqa: BLE001
            row = {"ok": False, "failed": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-400:]}
        rows.append({**{k: v for k, v in asdict(spec).items() if k not in ("label",)}, "label": spec.label,
                     "variant": name, "prior_rmse_px": round(prior["rmse_px"], 2), **row})
    return rows


def sweep(cases: list[tuple[Spec, dict[str, dict]]], workers: int = 6, name: str = "bench") -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    t0 = time.time()
    with ProcessPoolExecutor(workers) as pool:
        for i, part in enumerate(pool.map(run_case, cases)):
            rows.extend(part)
            if (i + 1) % 5 == 0 or i + 1 == len(cases):
                print(f"[{name}] {i + 1}/{len(cases)} cases, {time.time() - t0:.0f}s", flush=True)
    (OUT / f"{name}.json").write_text(json.dumps(rows, indent=1, default=float))
    return rows


def summarize(rows: list[dict], by: str) -> str:
    """Table: for each value of `by` and each variant: success rate and median RMSE (px) over seeds."""
    values = sorted({r[by] if not isinstance(r[by], (list, tuple)) else tuple(r[by]) for r in rows}, key=str)
    variants = sorted({r["variant"] for r in rows})
    lines = [f"{by:>18s} | " + " | ".join(f"{v:>26s}" for v in variants)]
    for val in values:
        cells = []
        for v in variants:
            sel = [r for r in rows if (tuple(r[by]) if isinstance(r[by], (list, tuple)) else r[by]) == val and r["variant"] == v]
            if not sel:
                cells.append(f"{'-':>26s}")
                continue
            ok = np.mean([bool(r.get("ok")) for r in sel])
            errs = [r["rmse_px"] for r in sel if r.get("rmse_px") is not None]
            med = f"{np.median(errs):.2f}px" if errs else "  -  "
            cells.append(f"{ok * 100:4.0f}% ok, med {med:>8s} (n={len(sel)})")
        lines.append(f"{str(val):>18s} | " + " | ".join(f"{c:>26s}" for c in cells))
    return "\n".join(lines)
