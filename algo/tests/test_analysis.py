"""Tests for geometry.analysis -- transform diagnostics. Synthetic data only."""

from __future__ import annotations

import numpy as np

from algo.geometry.analysis import (
    apply_homography,
    decompose_transform,
    distinct_anchors,
    health_checks,
    local_scale,
    prior_offsets,
)


def _similarity(scale: float, deg: float, tx: float = 0.0, ty: float = 0.0) -> np.ndarray:
    t = np.radians(deg)
    return np.array([[scale * np.cos(t), -scale * np.sin(t), tx], [scale * np.sin(t), scale * np.cos(t), ty], [0, 0, 1]])


def test_decompose_similarity_recovers_scale_and_rotation():
    d = decompose_transform(_similarity(1.2, 30))
    assert abs(d["sigma_major"] - 1.2) < 1e-9 and abs(d["sigma_minor"] - 1.2) < 1e-9
    assert abs(d["condition"] - 1.0) < 1e-9
    assert abs(d["rotation_deg"] - 30) < 1e-6
    assert not d["reflected"]


def test_decompose_flags_collapsed_and_mirrored_transforms():
    collapsed = np.array([[3.4, 0, 0], [0, 0.03, 0], [0, 0, 1.0]])
    assert decompose_transform(collapsed)["condition"] < 0.02
    assert decompose_transform(np.diag([1.0, -1.0, 1.0]))["reflected"]


def test_local_scale_matches_affine_scale():
    assert abs(local_scale(_similarity(2.0, 10), 50, 80) - 2.0) < 1e-9


def test_distinct_anchors_merges_near_duplicates():
    pts = np.array([[0, 0], [2, 1], [100, 100], [101, 99], [500, 20]], dtype=float)
    assert distinct_anchors(pts, tol=15) == [0, 2, 4]


def test_prior_offsets_are_zero_for_points_on_the_prior():
    prior = _similarity(1.0, 0, 10, 20)
    src = np.array([[0.0, 0.0], [5.0, 5.0]])
    assert np.allclose(prior_offsets(prior, src, apply_homography(prior, src)), 0)


def _checks_by_label(checks):
    return {c["label"]: c["ok"] for c in checks}


def test_health_checks_pass_for_a_sane_fit():
    rng = np.random.default_rng(0)
    src = rng.uniform(0, 4000, size=(12, 2))
    H = _similarity(1.0, 2, 300, 500)
    ref = apply_homography(H, src) + rng.normal(0, 0.3, src.shape)
    ok = _checks_by_label(health_checks(H, src, ref, 0.5, 1.0, H @ _similarity(1, 0, 40, -10)))
    assert all(v for v in ok.values()), ok


def test_health_checks_fail_for_a_collapsed_fit_that_scores_low_rmse():
    rng = np.random.default_rng(1)
    src = rng.uniform(0, 4000, size=(12, 2))
    collapsed = np.array([[3.4, 0, 100], [0, 0.03, 200], [0, 0, 1.0]])
    ref = apply_homography(collapsed, src)  # reprojection error is ~0 by construction
    ok = _checks_by_label(health_checks(collapsed, src, ref, 0.1, 1.18, _similarity(1.18, 0, 0, 0)))
    assert ok["Low reprojection error"] is True
    assert ok["Transform is well-conditioned"] is False
    assert ok["Scale matches the GSD ratio"] is False
    assert ok["Agrees with the control-grid prior"] is False
