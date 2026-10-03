"""Run every project config through the pipeline, one process each, and record each as a run the desktop
app can show (data/results/<run_id>/meta.json), plus a one-line summary per project.

    python scripts/run_all.py [config.yaml ...]     (default: all of configs/)
    -> data/results/run_all_summary.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT.parent / "data" / "results"


def main() -> None:
    names = sys.argv[1:] or sorted(p.name for p in (ROOT / "configs").glob("*.yaml"))
    summary_path = RESULTS / "run_all_summary.json"
    previous = {r["config"]: r for r in json.loads(summary_path.read_text(encoding="utf-8"))} if summary_path.exists() else {}
    summary = []
    for i, name in enumerate(names):
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = RESULTS / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc).isoformat()
        meta = {"run_id": run_id, "config": name, "status": "running", "started_at": started, "finished_at": None}
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        t0 = time.time()
        with open(run_dir / "run.log", "w") as log:
            rc = subprocess.run([sys.executable, "-m", "algo.pipeline", "--config", f"configs/{name}", "--run-id", run_id],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        meta["status"] = "done" if rc == 0 else "error"
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        if rc != 0:
            meta["stderr_tail"] = (run_dir / "run.log").read_text(errors="replace")[-4000:]
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        mp = run_dir / "metrics.json"
        m = json.loads(mp.read_text()) if mp.exists() else {}
        row = {"config": name, "run_id": run_id, "status": meta["status"], "seconds": round(time.time() - t0, 1),
               "matches": m.get("match_count"), "inliers": m.get("inlier_count"), "rmse_m": m.get("rmse_m"),
               "heldout_rmse_m": m.get("heldout_rmse_m"), "structure": m.get("structure"), "failure": m.get("failure")}
        previous[name] = row
        summary = list(previous.values())
        print(f"[{i + 1}/{len(names)}] {name:28s} {row['status']:5s} {row['seconds']:6.1f}s  matches={row['matches']} "
              f"inliers={row['inliers']} rmse_m={row['rmse_m']} heldout_m={row['heldout_rmse_m']} struct={row['structure']} "
              f"{('FAIL: ' + row['failure'][:90]) if row['failure'] else ''}", flush=True)
        summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
