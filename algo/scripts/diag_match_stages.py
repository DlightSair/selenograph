"""Diagnostic: instrument pipeline.run()'s internals to see how many
candidate matches survive each stage (crater matching, relief weighting,
consistency boost, ANMS, first MAGSAC fit, refine/densify, second MAGSAC
fit) and how long each stage takes. Not part of the pipeline -- a trace for
tuning the accuracy-improvement stages added on top of the real end-to-end
run. See CLAUDE.md.

Usage: python -u scripts/diag_match_stages.py [config_name]   (-u so timing
prints show up immediately instead of waiting for Python's full-buffering on
a redirected stdout to flush; config_name is a file under configs/, default
"default.yaml")
"""

import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import yaml

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from algo.geometry.consistency import boost_by_global_consistency
from algo.geometry.refine import refine_and_densify
from algo.geometry.robust_fit import fit_transform
from algo.matching.classical import enforce_uniform_distribution, match_classical
from algo.matching.crater import match_crater
from algo.matching.match import Match
from algo.pipeline import _find_source_label_and_grid
from algo.preprocessing.grid import (
    crop_reference_to_window,
    crop_source_to_aoi,
    load_geometry_grid,
    reference_window_for_source_window,
)
from algo.preprocessing.metadata import load_metadata
from algo.preprocessing.relief import apply_relief_risk_weighting
from algo.pyramid.coarse_to_fine import align_coarse_to_fine

_start = time.time()


def _mark(label: str) -> None:
    print(f"[{time.time() - _start:7.1f}s] {label}", flush=True)


ROOT = Path(__file__).parents[1]
config_name = sys.argv[1] if len(sys.argv) > 1 else "default.yaml"
with open(ROOT / "configs" / config_name) as f:
    config = yaml.safe_load(f)

source_meta, reference_meta = load_metadata(config["source"], config["reference"])
label_path, grid_csv = _find_source_label_and_grid(config["source"])
aoi = config["aoi"]
source_crop, source_window = crop_source_to_aoi(
    label_path, grid_csv, aoi["lat_min"], aoi["lat_max"], aoi["lon_min"], aoi["lon_max"]
)
_mark(f"source cropped: {source_crop.shape}")

grid = load_geometry_grid(grid_csv)
with rasterio.open(config["reference"]["path"]) as ds:
    reference_transform, reference_crs = ds.transform, ds.crs
reference_window = reference_window_for_source_window(grid, source_window, reference_transform, reference_crs)
reference_crop = crop_reference_to_window(config["reference"]["path"], reference_window)
reference_row_offset, reference_col_offset = reference_window[0], reference_window[2]
_mark(f"reference cropped: {reference_crop.shape}")

levels = align_coarse_to_fine(
    source_crop.astype(np.float64), reference_crop, source_meta.gsd, reference_meta.gsd, config["pyramid"]
)
_mark(f"levels: {len(levels)} -> gsds={[round(l.level_gsd, 1) for l in levels]}")

matches = []
for li, level in enumerate(levels):
    _mark(f"level {li} start (gsd={level.level_gsd:.1f}m, tile={level.source_tile.shape}/{level.reference_tile.shape})")

    classical = match_classical(level, config["matching"])
    _mark(f"  classical done: {len(classical)}")

    crater = match_crater(level, config["matching"])
    _mark(f"  crater done: {len(crater)}")

    level_matches = classical + crater
    for m in level_matches:
        matches.append(
            Match(
                (m.source_xy[0] * level.source_scale, m.source_xy[1] * level.source_scale),
                (
                    m.reference_xy[0] * level.reference_scale + reference_col_offset,
                    m.reference_xy[1] * level.reference_scale + reference_row_offset,
                ),
                m.confidence,
            )
        )

_mark(f"total candidate matches: {len(matches)}")

dem_cfg = config.get("dem", {})
if dem_cfg.get("enabled"):
    matches = apply_relief_risk_weighting(matches, reference_transform, reference_crs, dem_cfg["path"])
    _mark(f"after relief weighting: {len(matches)}")

before_consistency = len(matches)
matches = boost_by_global_consistency(matches)
_mark(f"after consistency boost: {len(matches)} (was {before_consistency})")

matches = enforce_uniform_distribution(matches, config["anms"])
_mark(f"after ANMS: {len(matches)}")

transform, inliers = fit_transform(matches, config["geometry"])
_mark(f"first MAGSAC fit: {len(inliers)} inliers / {len(matches)} candidates")

if transform is not None and len(inliers) >= 4:
    refined_matches = refine_and_densify(
        inliers, source_crop, reference_crop, transform, source_meta.gsd, reference_meta.gsd,
        reference_row_offset, reference_col_offset,
    )
    _mark(f"refine_and_densify: {len(refined_matches)} points (from {len(inliers)} inliers)")
    refined_transform, refined_inliers = fit_transform(refined_matches, config["geometry"])
    _mark(f"second MAGSAC fit: {len(refined_inliers)} inliers / {len(refined_matches)} candidates")
