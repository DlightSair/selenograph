"""Generates the match-overlay PNG for a completed run, on demand. Adapted
from scripts/visualize_run.py: that script is a manual diagnostic hardcoded
to configs/default.yaml; this module is the same side-by-side plot but
config-agnostic, so the API server can render an overlay for any run
regardless of which AOI config produced it.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — this runs inside the API server process, no display
import matplotlib.pyplot as plt
import numpy as np

from algo.api._crops import load_aoi_context


def generate_overlay(config: dict, run_id: str, force: bool = False) -> Path:
    """Renders matches.csv for `run_id` as a side-by-side source/reference
    plot and caches it as overlay_matches.png next to the run's other
    outputs. Assumes the process cwd is algo/ (same as pipeline.run), so the
    config's relative source/reference/output_dir paths resolve correctly."""
    output_dir = Path(config["evaluation"]["output_dir"]) / run_id
    out_path = output_dir / "overlay_matches.png"
    if out_path.exists() and not force:
        return out_path

    matches_path = output_dir / "matches.csv"
    with open(matches_path, newline="") as f:
        rows = list(csv.DictReader(f))

    ctx = load_aoi_context(config, decimation="auto")
    source_crop, reference_crop = ctx.source_crop, ctx.reference_crop
    ref_row_offset, ref_col_offset = ctx.reference_row_offset, ctx.reference_col_offset
    s_inv = np.linalg.inv(ctx.source_to_full)

    fig, (ax_s, ax_r) = plt.subplots(1, 2, figsize=(14, 10))
    ax_s.imshow(source_crop, cmap="gray")
    ax_s.set_title(f"Source crop {source_crop.shape} (decimated x{ctx.decimation:.0f})")
    ax_r.imshow(reference_crop, cmap="gray")
    ax_r.set_title(f"Reference crop {reference_crop.shape}")

    colors = plt.cm.tab10(np.linspace(0, 1, max(len(rows), 1)))
    for row, color in zip(rows, colors):
        sx, sy = (s_inv @ np.array([float(row["source_x"]), float(row["source_y"]), 1.0]))[:2]
        rx, ry = float(row["reference_x"]) - ref_col_offset, float(row["reference_y"]) - ref_row_offset
        ax_s.plot(sx, sy, "o", color=color, markersize=8, markeredgecolor="white")
        ax_r.plot(rx, ry, "o", color=color, markersize=8, markeredgecolor="white")

    plt.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
