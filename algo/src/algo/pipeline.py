"""End-to-end orchestration of the registration pipeline. See docs/architecture.md.

Stage order in practice differs slightly from the original design sketch:
illumination normalization (Stage 1) runs lazily per pyramid level inside
the classical matcher rather than once upfront, since it's cheap only on
the much-smaller per-level tiles, not the full multi-hundred-megapixel
source crop.
"""

import argparse
from pathlib import Path

import numpy as np
import rasterio
import yaml

from algo.evaluation.metrics import evaluate
from algo.geometry.robust_fit import fit_transform
from algo.matching.classical import enforce_uniform_distribution, match_classical
from algo.matching.learned import Match, match_learned
from algo.preprocessing.grid import crop_source_to_aoi
from algo.preprocessing.metadata import load_metadata
from algo.pyramid.coarse_to_fine import align_coarse_to_fine
from algo.utils.io import find_pds4_product


def _find_source_label_and_grid(source_cfg: dict) -> tuple[Path, Path]:
    product_dir = Path(source_cfg["path"])
    _data_path, label_path = find_pds4_product(product_dir)
    grid_csv = next((product_dir / "geometry").rglob("*.csv"))
    return label_path, grid_csv


def _load_reference_gray(reference_cfg: dict) -> np.ndarray:
    with rasterio.open(reference_cfg["path"]) as ds:
        bands = ds.read()
    return bands[:3].mean(axis=0)


def run(config: dict) -> dict:
    source_meta, reference_meta = load_metadata(config["source"], config["reference"])

    label_path, grid_csv = _find_source_label_and_grid(config["source"])
    aoi = config["aoi"]
    source_crop, _crop_offset = crop_source_to_aoi(
        label_path, grid_csv, aoi["lat_min"], aoi["lat_max"], aoi["lon_min"], aoi["lon_max"]
    )
    reference_gray = _load_reference_gray(config["reference"])

    levels = align_coarse_to_fine(
        source_crop.astype(np.float64), reference_gray, source_meta.gsd, reference_meta.gsd, config["pyramid"]
    )

    matches = []
    for level in levels:
        try:
            learned = match_learned(level, config["matching"])
        except NotImplementedError:
            learned = []

        threshold = config["matching"]["confidence_threshold"]
        kept_learned = [m for m in learned if m.confidence >= threshold]
        level_matches = list(kept_learned)
        if len(kept_learned) < len(learned) or not learned:
            level_matches += match_classical(level, config["matching"])

        # Rescale from level-local pixel coords back to crop-native / reference-native coords.
        for m in level_matches:
            matches.append(
                Match(
                    (m.source_xy[0] * level.source_scale, m.source_xy[1] * level.source_scale),
                    (m.reference_xy[0] * level.reference_scale, m.reference_xy[1] * level.reference_scale),
                    m.confidence,
                )
            )

    matches = enforce_uniform_distribution(matches, config["anms"])
    transform, inliers = fit_transform(matches, config["geometry"])

    return evaluate(matches, inliers, transform, config["evaluation"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    results = run(config)
    print(results)


if __name__ == "__main__":
    main()
