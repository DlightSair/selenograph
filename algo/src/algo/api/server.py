"""Local HTTP API wrapping algo.pipeline.run, so a desktop (or future web) UI
can trigger registration runs and fetch results without embedding Python.
Each run executes as a subprocess of this same interpreter -- a crash inside
one run can't take the server down, and it's the same invocation documented
in the README (`python -m algo.pipeline --config ...`), just launched for you.

Run with (from algo/, inside its venv):
    ./.venv/Scripts/python.exe -m algo.api.server
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from algo.api.overlay import generate_overlay
from algo.api.preview import generate_preview
from algo.api.visualization import generate_visualizations, viz_image_path
from algo.preprocessing.metadata import load_metadata

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    # Packaged app: keep user data outside the install folder, in the same layout the repo uses
    # (<home>/algo/configs, <home>/data/results) so every relative path in a config keeps working.
    _HOME = Path(os.environ.get("SELENOGRAPH_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Selenograph")
    ROOT = _HOME / "algo"
    (ROOT / "configs").mkdir(parents=True, exist_ok=True)
    (_HOME / "data" / "results").mkdir(parents=True, exist_ok=True)
else:
    ROOT = Path(__file__).resolve().parents[3]  # algo/src/algo/api/server.py -> algo/
os.chdir(ROOT)  # configs/*.yaml use paths relative to algo/, same as the CLI

CONFIGS_DIR = ROOT / "configs"
RESULTS_DIR = (ROOT / "../data/results").resolve()

app = FastAPI(title="lunar-registration-api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # localhost-only server; open for the desktop app and a future web demo
    allow_methods=["*"],
    allow_headers=["*"],
)

_run_lock = threading.Lock()
_BOOT_TIME = datetime.now(timezone.utc)
_children: list = []  # pipeline subprocesses started by this server (killed if the app goes away)
_active_runs: set[str] = set()  # runs whose subprocess this server process is watching


class RunRequest(BaseModel):
    config: str = "default.yaml"


class CreateConfigRequest(BaseModel):
    name: str
    aoi_name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    source_instrument: str = "TMC2"
    source_path: str
    reference_path: str
    dem_enabled: bool = False
    dem_path: str | None = None


def _config_path(name: str) -> Path:
    safe_name = Path(name).name  # strip any directory components — reject path traversal
    path = CONFIGS_DIR / safe_name
    if not path.is_file() or path.suffix != ".yaml":
        raise HTTPException(404, f"no such config: {name}")
    return path


def _load_config(name: str) -> dict:
    return yaml.safe_load(_config_path(name).read_text())


def _load_run(run_id: str, full: bool = True) -> dict:
    run_dir = RESULTS_DIR / Path(run_id).name  # Path(...).name again blocks traversal via run_id
    if not run_dir.is_dir():
        raise HTTPException(404, f"no such run: {run_id}")

    meta = {"run_id": run_id, "status": "unknown", "config": None}
    meta_path = run_dir / "meta.json"
    if meta_path.exists():
        meta.update(json.loads(meta_path.read_text()))

    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else None

    if meta["status"] == "running" and run_id not in _active_runs:
        # Started by an earlier server process that has since exited (e.g. restarted
        # mid-run): its watcher thread died with it, so nothing would ever update this
        # record and the UI would show "running" forever.
        started = meta.get("started_at")
        if started is None or datetime.fromisoformat(started) < _BOOT_TIME:
            meta["status"] = "done" if metrics is not None else "error"
            meta["finished_at"] = datetime.now(timezone.utc).isoformat()
            if metrics is None:
                meta["stderr_tail"] = "Run was interrupted: the server restarted while it was running."
            meta_path.write_text(json.dumps(meta, indent=2))

    # transform.json is ~1 MB per run; only the single-run view needs it, not the list.
    transform_path = run_dir / "transform.json"
    transform = json.loads(transform_path.read_text()) if full and transform_path.exists() else None

    stage = None
    if meta["status"] == "running":
        stage = "Writing output" if metrics is not None else "Matching"
    return {**meta, "metrics": metrics, "transform": transform, "stage": stage}


def _start_run(config_name: str) -> str:
    _config_path(config_name)  # validate before spawning anything
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _active_runs.add(run_id)

    meta_path = run_dir / "meta.json"
    meta_path.write_text(json.dumps({
        "run_id": run_id,
        "config": config_name,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }, indent=2))

    log_path = run_dir / "run.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        ([sys.executable, "--run-pipeline"] if FROZEN else [sys.executable, "-m", "algo.pipeline"]) + ["--config", f"configs/{config_name}", "--run-id", run_id],
        cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT,
    )

    _children.append(proc)

    def _watch() -> None:
        proc.wait()
        log_file.close()
        _active_runs.discard(run_id)
        meta = json.loads(meta_path.read_text())
        meta["status"] = "done" if proc.returncode == 0 else "error"
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        if proc.returncode != 0:
            meta["stderr_tail"] = log_path.read_text(errors="replace")[-4000:]
        meta_path.write_text(json.dumps(meta, indent=2))
        if proc.returncode == 0:
            try:  # warm the caches so "View results" opens instantly
                cfg = _load_config(config_name)
                generate_overlay(cfg, run_id)
                generate_visualizations(cfg, run_id)
            except Exception:  # noqa: BLE001 -- best effort; the endpoints render on demand
                pass

    threading.Thread(target=_watch, daemon=True).start()
    return run_id


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "selenograph"}


@app.get("/configs")
def list_configs() -> list[dict]:
    out = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        cfg = yaml.safe_load(path.read_text())
        out.append({
            "name": path.name,
            "aoi_name": cfg["aoi"]["name"],
            "lat_min": cfg["aoi"]["lat_min"],
            "lat_max": cfg["aoi"]["lat_max"],
            "lon_min": cfg["aoi"]["lon_min"],
            "lon_max": cfg["aoi"]["lon_max"],
            "source_instrument": cfg["source"]["instrument"],
            "source_path": cfg["source"]["path"],
            "reference_path": cfg["reference"]["path"],
            "dem_enabled": cfg.get("dem", {}).get("enabled", False),
        })
    return out


@app.post("/configs")
def create_config(req: CreateConfigRequest) -> dict:
    safe_name = Path(req.name).name  # strip any directory components — reject path traversal
    if not safe_name or any(c in safe_name for c in "\\/:*?\"<>|"):
        raise HTTPException(400, "invalid project name")

    config_path = CONFIGS_DIR / f"{safe_name}.yaml"
    if config_path.exists():
        raise HTTPException(409, f"a project named '{safe_name}' already exists")

    if req.lat_min >= req.lat_max:
        raise HTTPException(400, "lat_min must be less than lat_max")
    if req.lon_min >= req.lon_max:
        raise HTTPException(400, "lon_min must be less than lon_max")
    if not (-90 <= req.lat_min <= 90 and -90 <= req.lat_max <= 90):
        raise HTTPException(400, "latitude must be between -90 and 90")
    if not (0 <= req.lon_min <= 360 and 0 <= req.lon_max <= 360):
        raise HTTPException(400, "longitude must be between 0 and 360 (this project's convention)")

    source_abs = (ROOT / req.source_path).resolve()
    if not source_abs.is_dir():
        raise HTTPException(400, f"source path does not exist or is not a directory: {req.source_path}")
    reference_abs = (ROOT / req.reference_path).resolve()
    if not reference_abs.is_file():
        raise HTTPException(400, f"reference path does not exist or is not a file: {req.reference_path}")

    dem_section: dict = {"enabled": req.dem_enabled}
    if req.dem_enabled:
        if not req.dem_path:
            raise HTTPException(400, "dem_path is required when dem_enabled is true")
        dem_abs = (ROOT / req.dem_path).resolve()
        if not dem_abs.is_file():
            raise HTTPException(400, f"dem path does not exist: {req.dem_path}")
        dem_section["path"] = req.dem_path

    config = {
        "aoi": {
            "name": req.aoi_name,
            "lat_min": req.lat_min,
            "lat_max": req.lat_max,
            "lon_min": req.lon_min,
            "lon_max": req.lon_max,
        },
        "source": {
            "instrument": req.source_instrument,
            "product_type": "calibrated",
            "path": req.source_path,
        },
        "reference": {
            "provider": "user_supplied",
            "layer": safe_name,
            "path": req.reference_path,
        },
        "dem": dem_section,
        "evaluation": {"output_dir": "../data/results/"},
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return {"name": config_path.name}


@app.get("/footprint")
def get_footprint(path: str) -> dict:
    """Lat/lon bounding box of a source product, from its control grid (or label corners)."""
    from algo.api._crops import find_source_label_and_grid
    from algo.preprocessing.grid import load_geometry_grid
    try:
        _label, grid = find_source_label_and_grid({"path": path})
        if not hasattr(grid, "lats"):
            grid = load_geometry_grid(grid)
    except Exception as e:
        raise HTTPException(400, f"cannot read footprint: {e}")
    return {"lat_min": float(grid.lats.min()), "lat_max": float(grid.lats.max()),
            "lon_min": float(grid.lons.min()), "lon_max": float(grid.lons.max())}


@app.get("/configs/{name}/details")
def get_config_details(name: str) -> dict:
    """Facts read from the actual source/reference products (not the config
    file): pixel size, dimensions, sun angles -- for the project info panel."""
    config = _load_config(name)
    source, reference = load_metadata(config["source"], config["reference"])
    reg = config.get("registration", {})
    return {
        "source": {
            "instrument": config["source"].get("instrument"),
            "gsd": source.gsd,
            "sun_elevation": source.sun_elevation,
            "sun_azimuth": source.sun_azimuth,
            "lines": source.shape[0] if source.shape else None,
            "samples": source.shape[1] if source.shape else None,
            "roll": source.roll,
            "pitch": source.pitch,
            "yaw": source.yaw,
            "altitude_km": source.altitude_km,
            "camera": source.camera,
        },
        "reference": {
            "gsd": reference.gsd,
            "rows": reference.shape[0] if reference.shape else None,
            "cols": reference.shape[1] if reference.shape else None,
            "provider": config["reference"].get("provider"),
            "layer": config["reference"].get("layer"),
        },
        "registration": {
            "mode": reg.get("mode", "prior_guided"),
            "relit": bool((reg.get("relit") or {}).get("enabled", False)),
            "dem": bool(config.get("dem", {}).get("enabled", False) or (reg.get("relit") or {}).get("dem")),
            "nonrigid": bool(reg.get("nonrigid", True)),
        },
    }


@app.get("/benchmarks")
def get_benchmarks() -> dict:
    """The synthetic ground-truth benchmark (see algo.benchmark): success rate / error per variation level
    and algorithm variant. Produced by `python -m algo.benchmark.report`."""
    path = RESULTS_DIR.parent / "benchmark" / "summary.json"
    if not path.is_file():
        raise HTTPException(404, "no benchmark has been run yet (python -m algo.benchmark.suites <suite>)")
    return json.loads(path.read_text())


@app.get("/configs/{name}/preview.png")
def get_preview(name: str):
    config = _load_config(name)
    try:
        path = generate_preview(config, Path(name).stem)
    except FileNotFoundError as e:
        raise HTTPException(500, f"could not render preview: {e}") from e
    return FileResponse(path, media_type="image/png")


@app.post("/runs")
def create_run(req: RunRequest) -> dict:
    with _run_lock:  # one run at a time — these are heavy (rasterio, NCC matching), no point racing them
        run_id = _start_run(req.config)
    return {"run_id": run_id, "status": "running"}


@app.get("/runs")
def list_runs(limit: int = 50, config: str | None = None) -> list[dict]:
    run_ids = sorted((p.name for p in RESULTS_DIR.iterdir() if p.is_dir()), reverse=True)
    out = []
    for run_id in run_ids:
        run = _load_run(run_id, full=False)
        if config is None or run.get("config") == config:
            out.append(run)
            if len(out) >= limit:
                break
    return out


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _load_run(run_id)


@app.get("/runs/{run_id}/overlay.png")
def get_overlay(run_id: str):
    run = _load_run(run_id)
    if run["status"] != "done":
        raise HTTPException(409, f"run {run_id} is {run['status']}, not done yet")
    config = _load_config(run["config"])
    try:
        path = generate_overlay(config, run_id)
    except FileNotFoundError as e:
        raise HTTPException(500, f"could not render overlay: {e}") from e
    return FileResponse(path, media_type="image/png")


def _done_run_config(run_id: str) -> dict:
    run = _load_run(run_id)
    if run["status"] != "done":
        raise HTTPException(409, f"run {run_id} is {run['status']}, not done yet")
    return _load_config(run["config"])


@app.get("/runs/{run_id}/viz")
def get_visualizations(run_id: str) -> dict:
    config = _done_run_config(run_id)
    try:
        return generate_visualizations(config, run_id)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/runs/{run_id}/viz/{name}.png")
def get_visualization_image(run_id: str, name: str):
    config = _done_run_config(run_id)
    try:
        return FileResponse(viz_image_path(config, run_id, Path(name).name), media_type="image/png")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


def _parent_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes

    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT: still running
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _exit_with_parent(pid: int) -> None:
    """The packaged server is private to the desktop app: when the app exits (even by crashing) stop any
    running registration and exit, so nothing is left running in the background."""
    import time

    while _parent_alive(pid):
        time.sleep(2)
    for proc in _children:
        if proc.poll() is None:
            proc.kill()
    os._exit(0)


def main(port: int = 8000, parent_pid: int | None = None) -> None:
    import uvicorn

    if parent_pid:
        threading.Thread(target=_exit_with_parent, args=(parent_pid,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning" if FROZEN else "info")


if __name__ == "__main__":
    main()
