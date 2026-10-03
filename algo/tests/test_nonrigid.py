"""geometry.nonrigid: a smooth residual field is recovered when present and rejected when it is not."""

from __future__ import annotations

import numpy as np

from algo.geometry.analysis import apply_homography
from algo.geometry.nonrigid import NonRigidModel, fit_nonrigid


def _scene(rng, field_amp: float, noise: float, n: int = 1500):
    H = np.array([[1.02, 0.01, 40.0], [-0.01, 1.01, 25.0], [0, 0, 1.0]])
    src = rng.uniform(0, 3000, (n, 2))
    p = apply_homography(H, src)
    # smooth, non-linear displacement: long-wavelength bending plus a ripple along the strip
    d = np.stack([
        field_amp * np.sin(p[:, 1] / 700.0) * np.cos(p[:, 0] / 900.0),
        field_amp * 0.6 * np.sin(p[:, 1] / 500.0 + 1.0),
    ], axis=1)
    ref = p + d + rng.normal(0, noise, p.shape)
    return H, src, ref, d


def test_recovers_a_smooth_field_and_beats_the_homography_on_held_out_points():
    rng = np.random.default_rng(0)
    H, src, ref, _ = _scene(rng, field_amp=4.0, noise=0.15)
    model = fit_nonrigid(src, ref, H)
    assert model.field_fn is not None, model.info
    assert model.info["cv_rmse_nonrigid_px"] < 0.5 * model.info["cv_rmse_homography_px"]

    test_src = rng.uniform(200, 2800, (400, 2))
    truth = apply_homography(H, test_src)
    truth = truth + np.stack([4.0 * np.sin(truth[:, 1] / 700.0) * np.cos(truth[:, 0] / 900.0), 2.4 * np.sin(truth[:, 1] / 500.0 + 1.0)], axis=1)
    err = np.hypot(*(model.to_reference(test_src) - truth).T)
    assert np.sqrt((err**2).mean()) < 0.5


def test_rejects_the_field_when_the_homography_already_explains_the_data():
    rng = np.random.default_rng(1)
    H, src, ref, _ = _scene(rng, field_amp=0.0, noise=0.2)
    model = fit_nonrigid(src, ref, H)
    assert model.field_fn is None
    assert "rejected" in model.info["nonrigid"]


def test_inverse_map_and_json_round_trip():
    rng = np.random.default_rng(2)
    H, src, ref, _ = _scene(rng, field_amp=3.0, noise=0.1)
    model = fit_nonrigid(src, ref, H)
    assert model.field_fn is not None
    pts = rng.uniform(300, 2700, (50, 2))
    back = model.to_source(model.to_reference(pts))
    assert np.abs(back - pts).max() < 0.05

    bounds = (float(ref[:, 0].min()) - 100, float(ref[:, 1].min()) - 100, float(ref[:, 0].max()) + 100, float(ref[:, 1].max()) + 100)
    loaded = NonRigidModel.from_dict(model.to_dict(bounds))
    inside = apply_homography(H, pts)
    assert np.abs(loaded.displacement(inside) - model.displacement(inside)).max() < 0.15


def test_warp_source_places_pixels_where_the_forward_map_says():
    import cv2

    H = np.array([[1.0, 0, 20.0], [0, 1.0, 10.0], [0, 0, 1.0]])
    model = NonRigidModel(H=H, field_fn=lambda p: np.tile([3.0, -2.0], (len(p), 1)))
    src = np.zeros((200, 300), np.float32)
    src[100, 150] = 1.0
    src = cv2.GaussianBlur(src, (0, 0), 2.0)
    warped, valid = model.warp_source(src, (260, 360))
    y, x = np.unravel_index(np.argmax(warped), warped.shape)
    assert abs(x - (150 + 20 + 3)) <= 1 and abs(y - (100 + 10 - 2)) <= 1
    assert valid[y, x]
