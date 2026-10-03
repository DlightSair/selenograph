"""Tests for geometry.warp -- the source-crop-into-reference-frame warp used
by api.registration_view. Synthetic data only, same style as
test_accuracy_stages.py."""

from __future__ import annotations

import numpy as np

from algo.geometry.warp import warp_source_into_reference_frame


def test_identity_transform_with_zero_offset_reproduces_source():
    source = np.zeros((40, 40), dtype=np.float32)
    source[10:20, 10:20] = 255.0
    reference = np.zeros((40, 40), dtype=np.float32)  # same shape, content irrelevant here

    identity = np.eye(3)
    warped, valid = warp_source_into_reference_frame(source, reference, identity, 0.0, 0.0)

    np.testing.assert_allclose(warped, source, atol=1e-5)
    assert valid.all()


def test_translation_transform_shifts_into_reference_frame():
    source = np.zeros((40, 40), dtype=np.float32)
    source[5:8, 5:8] = 100.0  # a small bright block near the top-left
    reference = np.zeros((60, 60), dtype=np.float32)

    # Homography mapping source_xy -> reference_xy = source_xy + (20, 30), i.e. what
    # fit_transform would produce for a pure translation with no raster-absolute offset.
    translation = np.array([[1.0, 0.0, 20.0], [0.0, 1.0, 30.0], [0.0, 0.0, 1.0]])
    warped, valid = warp_source_into_reference_frame(source, reference, translation, 0.0, 0.0)

    assert warped.shape == reference.shape
    # The bright block should now sit at (25:28, 35:38) in the warped array (col, row shifted).
    assert warped[35:38, 25:28].mean() > 90.0
    assert valid[35:38, 25:28].all()
    assert not valid[0, 0]  # top-left corner has no source coverage after the shift


def test_reference_crop_offset_is_subtracted_before_warping():
    """A homography expressed in the reference RASTER's absolute pixel frame
    (as robust_fit.fit_transform actually produces) must land correctly
    inside reference_crop once its own window offset is accounted for."""
    source = np.zeros((40, 40), dtype=np.float32)
    source[5:8, 5:8] = 100.0
    reference_crop = np.zeros((60, 60), dtype=np.float32)

    # Same translation as above, but expressed in absolute raster coordinates: the
    # reference_crop this source actually lands in starts at raster row 1000, col 2000.
    row_offset, col_offset = 1000.0, 2000.0
    absolute_translation = np.array(
        [[1.0, 0.0, 20.0 + col_offset], [0.0, 1.0, 30.0 + row_offset], [0.0, 0.0, 1.0]]
    )

    warped, valid = warp_source_into_reference_frame(
        source, reference_crop, absolute_translation, row_offset, col_offset
    )

    assert warped[35:38, 25:28].mean() > 90.0
    assert valid[35:38, 25:28].all()


def test_valid_mask_is_false_where_source_never_projects():
    source = np.full((20, 20), 50.0, dtype=np.float32)  # uniformly non-zero -- a real pixel value
    reference = np.zeros((20, 20), dtype=np.float32)

    # Shift far enough that none of the source lands inside the reference frame.
    far_translation = np.array([[1.0, 0.0, 1000.0], [0.0, 1.0, 1000.0], [0.0, 0.0, 1.0]])
    warped, valid = warp_source_into_reference_frame(source, reference, far_translation, 0.0, 0.0)

    assert not valid.any()
    assert warped.max() == 0.0  # border fill, not a stale/misleading source value
