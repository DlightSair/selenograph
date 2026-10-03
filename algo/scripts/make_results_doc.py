"""Write docs/results.md: one table of every project's latest run (matches, error, held-out accuracy, what
the matcher selected and used), straight from data/results/run_all_summary.json + each run's metrics.json,
so the numbers in the docs are the numbers the pipeline produced.

    python scripts/make_results_doc.py
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT.parent / "data" / "results"
DOCS = ROOT.parent / "docs"


def fmt(v, nd=1, unit=""):
    return "—" if v is None else f"{v:.{nd}f}{unit}"


def main() -> None:
    rows = json.loads((RESULTS / "run_all_summary.json").read_text(encoding="utf-8"))
    lines = ["# Real-data results", "",
             "Latest run of every project (`python scripts/run_all.py`). There is no ground truth for real pairs, so the numbers "
             "are consistency measures: **RMS** is the residual of the inlier tile matches against the fitted model; "
             "**held-out** is the same model's error on tiles it was *not* fitted to (blocked cross-validation); "
             "**cross-check** numbers (two independent references, wrong starting guesses) are in `data/results/cross_checks/`.", "",
             "| project | source | reference | scale (ref/src) | matches (inliers) | RMS | held-out | representation | re-lit DEM | non-rigid field | time |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cfg = yaml.safe_load((ROOT / "configs" / r["config"]).read_text())
        mp = RESULTS / r["run_id"] / "metrics.json"
        m = json.loads(mp.read_text()) if mp.exists() else {}
        src = f"{cfg['source']['instrument']} {m.get('source_gsd_m') or ''} m".strip()
        ref = f"{cfg['reference'].get('provider', '')} {fmt(m.get('reference_gsd_m'), 1)} m"
        scale = (m["reference_gsd_m"] / m["source_gsd_m"]) if m.get("reference_gsd_m") and m.get("source_gsd_m") else None
        if m.get("failure"):
            lines.append(f"| {cfg['aoi']['name']} | {src} | {ref} | {fmt(scale, 2)}x | **no reliable fit** | — | — | — | — | — | {r['seconds']:.0f} s |")
            lines.append(f"| ↳ | | | | _{m['failure']}_ | | | | | | |")
            continue
        nr = m.get("nonrigid") or {}
        field = (f"{m.get('nonrigid_field_rms_m'):.1f} m rms" if m.get("nonrigid_field_rms_m") is not None else "not needed")
        lines.append(
            f"| {cfg['aoi']['name']} | {src} | {ref} | {fmt(scale, 2)}x | {m.get('match_count')} ({m.get('inlier_count')}) | "
            f"{fmt(m.get('rmse_m'), 1, ' m')} | {fmt(m.get('heldout_rmse_m'), 1, ' m')} | {m.get('structure')} | "
            f"{'yes' if m.get('relit_layer') else 'no'} | {field} | {r['seconds']:.0f} s |"
        )
    lines += ["", "Held-out error is computed on cell-median residuals (a 48 px cell), so it is smoother than the per-tile RMS; "
              "read the two together. A reference mosaic's own pixel size (100 m for WAC) bounds what any of these can resolve."]
    DOCS.mkdir(exist_ok=True)
    (DOCS / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote docs/results.md")


if __name__ == "__main__":
    main()
