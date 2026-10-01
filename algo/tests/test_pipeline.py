"""Smoke tests for the pipeline wiring. Fill in as each stage gets implemented."""

import pytest


def test_pipeline_importable():
    from algo import pipeline  # noqa: F401


@pytest.mark.skip(reason="stages not implemented yet")
def test_run_end_to_end():
    from algo.pipeline import run

    config = {
        # minimal config for a future integration test against a small fixture AOI
    }
    results = run(config)

    assert "rmse" in results
    assert "inlier_ratio" in results
