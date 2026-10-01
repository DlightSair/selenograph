"""Diagnostic: plot a run's inlier matches as side-by-side lines between the
source crop and reference image. Not part of the pipeline -- a manual sanity
check while tuning Stage 2-5.

Usage: python scripts/visualize_run.py <run_id>
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import yaml

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from algo.pipeline import _find_source_label_and_grid, _load_reference_gray  # noqa: E402
from algo.preprocessing.grid import crop_source_to_aoi  # noqa: E402

ROOT = Path(__file__).parents[1]


def main(run_id: str):
    with open(ROOT / "configs" / "default.yaml") as f:
        config = yaml.safe_load(f)

    matches_path = Path(config["evaluation"]["output_dir"].replace("../", str(ROOT.parent) + "/")) / run_id / "matches.csv"
    with open(matches_path, newline="") as f:
        rows = list(csv.DictReader(f))

    label_path, grid_csv = _find_source_label_and_grid(config["source"])
    aoi = config["aoi"]
    source_crop, _offset = crop_source_to_aoi(
        label_path, grid_csv, aoi["lat_min"], aoi["lat_max"], aoi["lon_min"], aoi["lon_max"]
    )
    reference_gray = _load_reference_gray(config["reference"])

    fig, (ax_s, ax_r) = plt.subplots(1, 2, figsize=(14, 10))
    source_small = source_crop[::8, ::8]
    ax_s.imshow(source_small, cmap="gray")
    ax_s.set_title(f"Source crop {source_crop.shape} (shown at 1/8)")
    ax_r.imshow(reference_gray, cmap="gray")
    ax_r.set_title(f"Reference {reference_gray.shape}")

    colors = plt.cm.tab10(np.linspace(0, 1, max(len(rows), 1)))
    for row, color in zip(rows, colors):
        sx, sy = float(row["source_x"]) / 8, float(row["source_y"]) / 8
        rx, ry = float(row["reference_x"]), float(row["reference_y"])
        ax_s.plot(sx, sy, "o", color=color, markersize=10, markeredgecolor="white")
        ax_r.plot(rx, ry, "o", color=color, markersize=10, markeredgecolor="white")

    plt.tight_layout()
    out_path = matches_path.parent / "overlay_matches.png"
    plt.savefig(out_path, dpi=120)
    print(f"saved {out_path} ({len(rows)} matches plotted)")


if __name__ == "__main__":
    main(sys.argv[1])
