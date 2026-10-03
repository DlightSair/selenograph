"""Entry point of the packaged server: `selenograph-server.exe --port N --parent-pid P` serves the API for
the desktop app; with `--run-pipeline` (used by the server to start a run as a child process) it runs one
registration instead."""
import multiprocessing
import os
import sys
from pathlib import Path


def _isolate_environment() -> None:
    """Use only the data bundled with this build, whatever else is installed on the machine (QGIS and
    other GIS software export GDAL_DATA / PROJ_LIB / PYTHONPATH that would otherwise be picked up)."""
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    for var in ("PYTHONHOME", "PYTHONPATH", "PROJ_LIB", "GDAL_DRIVER_PATH", "GDAL_DATA", "PROJ_DATA"):
        os.environ.pop(var, None)
    gdal, proj = base / "rasterio" / "gdal_data", base / "rasterio" / "proj_data"
    if gdal.is_dir():
        os.environ["GDAL_DATA"] = str(gdal)
    if proj.is_dir():
        os.environ["PROJ_DATA"] = os.environ["PROJ_LIB"] = str(proj)


def _arg(name: str, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main() -> None:
    multiprocessing.freeze_support()
    _isolate_environment()
    if len(sys.argv) > 1 and sys.argv[1] == "--run-pipeline":
        sys.argv = ["pipeline"] + sys.argv[2:]
        from algo.pipeline import main as run_pipeline

        run_pipeline()
    else:
        from algo.api.server import main as serve

        parent = _arg("--parent-pid")
        serve(port=int(_arg("--port", 8000)), parent_pid=int(parent) if parent else None)


if __name__ == "__main__":
    main()
