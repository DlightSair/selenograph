"""Pre-render the result visualizations of the runs listed in data/results/run_all_summary.json, so the desktop
app opens them instantly instead of rendering on first view (a big strip takes minutes).

    python scripts/render_all_viz.py [run_all_summary.json]
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

from algo.api.visualization import generate_visualizations  # noqa: E402


def main() -> None:
    summary_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "data" / "results" / "run_all_summary.json"
    rows = json.loads(summary_path.read_text())
    for row in rows:
        if row["status"] != "done" or not row.get("inliers"):
            print(f"skip {row['config']}: {row.get('failure') or row['status']}", flush=True)
            continue
        cfg = yaml.safe_load((ROOT / "configs" / row["config"]).read_text())
        t0 = time.time()
        try:
            m = generate_visualizations(cfg, row["run_id"], force=True)
            print(f"{row['config']:28s} viz {time.time() - t0:5.0f}s  {m['verdict']}: {m['summary']}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{row['config']:28s} viz FAILED: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
