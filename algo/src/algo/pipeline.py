"""End-to-end orchestration of the registration pipeline. See docs/architecture.md."""

import argparse

import yaml

from algo.preprocessing.metadata import load_metadata
from algo.preprocessing.illumination import normalize_illumination
from algo.pyramid.coarse_to_fine import align_coarse_to_fine
from algo.matching.classical import match_classical
from algo.matching.learned import match_learned
from algo.geometry.robust_fit import fit_transform
from algo.evaluation.metrics import evaluate


def run(config: dict) -> dict:
    source_meta, reference_meta = load_metadata(config["source"], config["reference"])

    source_norm, reference_norm = normalize_illumination(
        config["source"], config["reference"], source_meta, reference_meta, config["dem"]
    )

    levels = align_coarse_to_fine(source_norm, reference_norm, config["pyramid"])

    matches = []
    for level in levels:
        learned = match_learned(level, config["matching"])
        low_conf = [m for m in learned if m.confidence < config["matching"]["confidence_threshold"]]
        if low_conf:
            matches += match_classical(level, low_conf, config["matching"])
        matches += [m for m in learned if m not in low_conf]

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
