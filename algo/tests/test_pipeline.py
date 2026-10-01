"""Smoke tests for the pipeline wiring."""

from pathlib import Path

import pytest
import yaml

CONFIG_PATH = Path(__file__).parents[1] / "configs" / "default.yaml"


def test_pipeline_importable():
    from algo import pipeline  # noqa: F401


def _default_config_data_available() -> bool:
    if not CONFIG_PATH.exists():
        return False
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return (
        Path(config["source"]["path"]).exists()
        and Path(config["reference"]["path"]).exists()
    )


@pytest.mark.skipif(not _default_config_data_available(), reason="real Tycho source/reference data not present")
def test_run_end_to_end():
    """Runs the real pipeline against the real Tycho source/reference pair
    configured in configs/default.yaml. Slow (~1min): windowed-reads a 1.7GB
    source strip, runs Gabor filtering + ORB matching. Match quality isn't
    asserted here (that's a tuning concern, not a wiring one) -- this only
    confirms every stage runs end-to-end without raising and returns the
    expected result shape."""
    from algo.pipeline import run

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    results = run(config)

    assert "rmse" in results
    assert "inlier_count" in results
    assert "inlier_ratio" in results
    assert "match_count" in results
