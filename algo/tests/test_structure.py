"""matching.structure representations and the scale / illumination handling built on them."""

from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

from algo.geometry.analysis import apply_homography
from algo.matching import structure
from algo.matching.prior_guided import SourcePyramid, match_prior_guided


def _texture(shape, sigma=3, seed=0):
    rng = np.random.default_rng(seed)
    t = gaussian_filter(rng.normal(size=shape), sigma).astype(np.float32)
    return (t - t.min()) / np.ptp(t) * 200 + 10


def test_joint_ncc_single_channel_equals_opencv_ccoeff_normed():
    rng = np.random.default_rng(1)
    win = rng.normal(size=(90, 110)).astype(np.float32)
    tmpl = win[20:60, 30:80].copy() + rng.normal(0, 0.1, (40, 50)).astype(np.float32)
    mine = structure.joint_ncc(win[..., None], tmpl[..., None])
    ref = cv2.matchTemplate(win, tmpl, cv2.TM_CCOEFF_NORMED)
    assert mine.shape == ref.shape
    assert np.abs(mine - ref).max() < 2e-3


def test_gradient_magnitude_survives_contrast_reversal_but_intensity_does_not():
    ref = _texture((260, 260))
    tmpl_true = ref[100:164, 100:164]
    inverted = 255.0 - tmpl_true  # shading polarity flip
    for mode, should_find in (("intensity", False), ("edges", True), ("cfog", True)):
        r = structure.joint_ncc(structure.features(ref, mode, norm_sigma=8), structure.features(inverted, mode, norm_sigma=8))
        _, _, _, (px, py) = cv2.minMaxLoc(r)
        found = abs(px - 100) <= 1 and abs(py - 100) <= 1
        assert found == should_find, (mode, (px, py))


def test_source_pyramid_levels_map_back_to_full_resolution():
    base = np.zeros((400, 600), np.float32)
    base[200, 300] = 1000.0  # one bright pixel at full-res (x=300, y=200)
    pyr = SourcePyramid(base)
    img, S = pyr.get(4.0)
    y, x = np.unravel_index(np.argmax(img), img.shape)
    full = apply_homography(S, np.array([[x, y]]))[0]
    assert np.abs(full - [300, 200]).max() <= 2.5  # within one block of the true position

    # a pre-decimated base keeps the mapping consistent
    dec = cv2.resize(base, (150, 100), interpolation=cv2.INTER_AREA)
    S0 = np.array([[4.0, 0, 1.5], [0, 4.0, 1.5], [0, 0, 1.0]])
    pyr2 = SourcePyramid(dec, S0)
    img2, S2 = pyr2.get(8.0)
    y, x = np.unravel_index(np.argmax(img2), img2.shape)
    assert np.abs(apply_homography(S2, np.array([[x, y]]))[0] - [300, 200]).max() <= 5.0


def _similarity(deg, tx, ty):
    t = np.radians(deg)
    return np.array([[np.cos(t), -np.sin(t), tx], [np.sin(t), np.cos(t), ty], [0, 0, 1.0]])


def test_source_coarser_than_reference_is_registered():
    """A 4x coarser source (IIRS-against-NAC situation): the reference must be reduced, not the source."""
    reference = _texture((1800, 1500), sigma=4, seed=5)
    h_true = _similarity(1.0, 40.0, 30.0)  # fine-res "source-grid" -> reference
    fine_source = cv2.warpPerspective(reference, np.linalg.inv(h_true), (1500, 1800), flags=cv2.INTER_LINEAR)
    k = 4
    coarse = cv2.resize(fine_source, (1500 // k, 1800 // k), interpolation=cv2.INTER_AREA)
    S = np.diag([k, k, 1.0])
    S[:2, 2] = 0.5 * k - 0.5
    H_true = h_true @ S  # coarse px -> reference px
    H_prior = _similarity(0.0, -12.0, 9.0) @ H_true
    matches, info = match_prior_guided(coarse, reference, H_prior, reference_gsd=5.0)
    assert matches, info
    src = np.array([m.source_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)
    ref = np.array([m.reference_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)
    fitted, mask = cv2.findHomography(src, ref, cv2.USAC_MAGSAC, 2.0)
    probes = np.array([[100.0, 150.0], [250.0, 300.0], [180.0, 400.0]])
    err = np.linalg.norm(apply_homography(fitted, probes) - apply_homography(H_true, probes), axis=1)
    assert err.max() < 2.0, err


def test_auto_representation_leaves_intensity_when_shading_is_flipped():
    reference = _texture((1500, 1100), sigma=3, seed=7)
    h_true = _similarity(0.5, 25.0, 15.0)
    source = cv2.warpPerspective(reference, np.linalg.inv(h_true), (1100, 1500), flags=cv2.INTER_LINEAR)
    source = 255.0 - source  # opposite polarity
    h_prior = _similarity(0.0, -15.0, 10.0) @ h_true
    matches, info = match_prior_guided(source, reference, h_prior, reference_gsd=5.0)
    assert matches, info
    assert info["structure_selected"] != "intensity", info["capture_candidates"]


def test_rescue_capture_recovers_a_badly_wrong_prior():
    """Prior ~2 km off, rotated 6 deg and 6% mis-scaled: beyond the normal capture window."""
    reference = _texture((3200, 2800), sigma=5, seed=11)
    h_true = _similarity(0.0, 120.0, 90.0)
    source = cv2.warpPerspective(reference, np.linalg.inv(h_true), (2400, 2800), flags=cv2.INTER_LINEAR)
    th = np.radians(6.0)
    s = 1.06
    c = np.array([1200.0, 1400.0])
    R = np.array([[s * np.cos(th), -s * np.sin(th), 0], [s * np.sin(th), s * np.cos(th), 0], [0, 0, 1.0]])
    Tc = np.array([[1, 0, c[0]], [0, 1, c[1]], [0, 0, 1.0]])
    H_prior = _similarity(0.0, 320.0, -280.0) @ h_true @ Tc @ R @ np.linalg.inv(Tc)
    matches, info = match_prior_guided(source, reference, H_prior, reference_gsd=5.0)
    assert matches, info
    src = np.array([m.source_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)
    ref = np.array([m.reference_xy for m in matches], dtype=np.float32).reshape(-1, 1, 2)
    fitted, _ = cv2.findHomography(src, ref, cv2.USAC_MAGSAC, 2.0)
    probes = np.array([[500.0, 500.0], [1500.0, 1400.0], [1000.0, 2200.0]])
    err = np.linalg.norm(apply_homography(fitted, probes) - apply_homography(h_true, probes), axis=1)
    assert err.max() < 2.0, err


def test_unlit_source_is_refused_up_front():
    reference = _texture((1500, 1100), sigma=3, seed=3)
    dark = np.ones((1500, 1100), np.float32)  # DN 1: the OHRC strip in permanent shadow
    matches, info = match_prior_guided(dark, reference, np.eye(3), reference_gsd=5.0)
    assert not matches and "no usable contrast" in info["failed"]


def test_rescue_search_alone_finds_rotation_scale_and_shift():
    """The wide-search fallback, called directly (the normal capture now copes with moderate errors itself)."""
    from algo.matching.prior_guided import RefLayer, SourcePyramid, _rescue_capture

    reference = _texture((3200, 2800), sigma=5, seed=11)
    h_true = _similarity(0.0, 120.0, 90.0)
    source = cv2.warpPerspective(reference, np.linalg.inv(h_true), (2400, 2800), flags=cv2.INTER_LINEAR)
    th, s, c = np.radians(6.0), 1.06, np.array([1200.0, 1400.0])
    R = np.array([[s * np.cos(th), -s * np.sin(th), 0], [s * np.sin(th), s * np.cos(th), 0], [0, 0, 1.0]])
    Tc = np.array([[1, 0, c[0]], [0, 1, c[1]], [0, 0, 1.0]])
    H_prior = _similarity(0.0, 320.0, -280.0) @ h_true @ Tc @ R @ np.linalg.inv(Tc)
    cands = [("intensity", {"intensity": 1.0}), ("edges", {"edges": 1.0})]
    found, info = _rescue_capture(SourcePyramid(source), [RefLayer(reference.astype(np.float32))], H_prior, 5.0, cands, 0.25)
    assert found is not None, info
    probes = np.array([[500.0, 500.0], [1500.0, 1400.0], [1000.0, 2200.0]])
    err = np.linalg.norm(apply_homography(found["H"], probes) - apply_homography(h_true, probes), axis=1)
    assert err.max() < 4.0, err
