"""Diagnostic: instrument pipeline.run()'s internals to see how many
candidate matches survive each stage (crater matching, relief weighting,
consistency boost, ANMS, first MAGSAC fit, refine/densify, second MAGSAC
fit). Not part of the pipeline -- a trace for tuning the accuracy-
improvement stages added on top of the real end-to-end run. See CLAUDE.md.

Usage: python scripts/_diag_stages.py
"""

import sys
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
from algo.matching.learned import Match, match_learned
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

ROOT = Path(__file__).parents[1]
with open(ROOT / "configs" / "default.yaml") as f:
    config = yaml.safe_load(f)

source_meta, reference_meta = load_metadata(config["source"], config["reference"])
label_path, grid_csv = _find_source_label_and_grid(config["source"])
aoi = config["aoi"]
source_crop, source_window = crop_source_to_aoi(
    label_path, grid_csv, aoi["lat_min"], aoi["lat_max"], aoi["lon_min"], aoi["lon_max"]
)
grid = load_geometry_grid(grid_csv)
with rasterio.open(config["reference"]["path"]) as ds:
    reference_transform, reference_crs = ds.transform, ds.crs
reference_window = reference_window_for_source_window(grid, source_window, reference_transform, reference_crs)
reference_crop = crop_reference_to_window(config["reference"]["path"], reference_window)
reference_row_offset, reference_col_offset = reference_window[0], reference_window[2]

levels = align_coarse_to_fine(
    source_crop.astype(np.float64), reference_crop, source_meta.gsd, reference_meta.gsd, config["pyramid"]
)
print(f"levels: {len(levels)} -> gsds={[round(l.level_gsd, 1) for l in levels]}")

matches = []
for li, level in enumerate(levels):
    try:
        learned = match_learned(level, config["matching"])
    except NotImplementedError:
        learned = []
    threshold = config["matching"]["confidence_threshold"]
    kept_learned = [m for m in learned if m.confidence >= threshold]
    classical = []
    if len(kept_learned) < len(learned) or not learned:
        classical = match_classical(level, config["matching"])
    crater = match_crater(level, config["matching"])
    print(f"level {li} (gsd={level.level_gsd:.1f}m, tile={level.source_tile.shape}/{level.reference_tile.shape}): "
          f"learned={len(learned)} kept_learned={len(kept_learned)} classical={len(classical)} crater={len(crater)}")

    level_matches = kept_learned + classical + crater
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

print(f"\ntotal candidate matches: {len(matches)}")

dem_cfg = config.get("dem", {})
if dem_cfg.get("enabled"):
    matches = apply_relief_risk_weighting(matches, reference_transform, reference_crs, dem_cfg["path"])
    print(f"after relief weighting: {len(matches)} (confidences adjusted, not filtered)")

before_consistency = len(matches)
matches = boost_by_global_consistency(matches)
print(f"after consistency boost: {len(matches)} (was {before_consistency})")

matches = enforce_uniform_distribution(matches, config["anms"])
print(f"after ANMS: {len(matches)}")

transform, inliers = fit_transform(matches, config["geometry"])
print(f"first MAGSAC fit: {len(inliers)} inliers / {len(matches)} candidates")

if transform is not None and len(inliers) >= 4:
    refined_matches = refine_and_densify(
        inliers, source_crop, reference_crop, transform, source_meta.gsd, reference_meta.gsd,
        reference_row_offset, reference_col_offset,
    )
    print(f"refine_and_densify: {len(refined_matches)} points (from {len(inliers)} inliers)")
    refined_transform, refined_inliers = fit_transform(refined_matches, config["geometry"])
    print(f"second MAGSAC fit: {len(refined_inliers)} inliers / {len(refined_matches)} candidates")
