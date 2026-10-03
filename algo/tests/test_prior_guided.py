"""Tests for matching.prior_guided: recover a known transform from a deliberately wrong prior.
Synthetic data only."""

from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

from algo.geometry.analysis import apply_homography
from algo.matching.prior_guided import _robust_translation, match_prior_guided


def _similarity(deg: float, tx: float, ty: float) -> np.ndarray:
    t = np.radians(deg)
    return np.array([[np.cos(t), -np.sin(t), tx], [np.sin(t), np.cos(t), ty], [0, 0, 1.0]])


def test_robust_translation_ignores_outliers():
    shifts = np.vstack([np.full((20, 2), [5.0, -3.0]) + np.random.default_rng(0).normal(0, 0.3, (20, 2)),
                        np.random.default_rng(1).uniform(-200, 200, (6, 2))])
    shift, agree = _robust_translation(shifts, radius=3.0)
    assert agree >= 20
    assert np.allclose(shift, [5.0, -3.0], atol=0.5)


def test_recovers_known_transform_from_a_wrong_prior():
    rng = np.random.default_rng(3)
    reference = gaussian_filter(rng.normal(size=(1500, 1100)), 3).astype(np.float32)
    reference = (reference - reference.min()) / np.ptp(reference) * 200 + 10

    h_true = _similarity(1.0, 30.0, 20.0)  # source px -> reference px
    source = cv2.warpPerspective(reference, np.linalg.inv(h_true), (1100, 1500), flags=cv2.INTER_LINEAR)
    source = source * 2.5 + 40  # different gain/offset, as between two sensors

    h_prior = _similarity(0.0, -20.0, 15.0) @ h_true  # prior is ~25 px off
    matches, info = match_prior_guided(source, reference, h_prior, reference_gsd=5.0)

    assert matches, info
    src = np.array([m.source_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)
    ref = np.array([m.reference_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)
    fitted, mask = cv2.findHomography(src, ref, cv2.USAC_MAGSAC, 2.0)
    assert fitted is not None and mask.sum() >= 10

    probes = np.array([[300.0, 400.0], [700.0, 900.0], [500.0, 1200.0]])
    err = np.linalg.norm(apply_homography(fitted, probes) - apply_homography(h_true, probes), axis=1)
    assert err.max() < 1.5, err


def test_reports_failure_instead_of_a_wrong_fit_on_unrelated_images():
    rng = np.random.default_rng(4)
    reference = gaussian_filter(rng.normal(size=(1500, 1100)), 3).astype(np.float32)
    unrelated = gaussian_filter(rng.normal(size=(1500, 1100)), 3).astype(np.float32)
    matches, info = match_prior_guided(unrelated, reference, np.eye(3), reference_gsd=5.0)
    assert not matches and "failed" in info
