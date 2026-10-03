import numpy as np

from algo.illumination.relight import cast_shadow_mask, render_dem


def test_flat_terrain_is_uniform():
    img = render_dem(np.zeros((120, 120), np.float32), 10.0, 90.0, 40.0)
    assert img[10:-10, 10:-10].std() < 1e-4


def test_slope_facing_sun_is_brighter_than_slope_facing_away():
    y, x = np.mgrid[0:200, 0:200].astype(np.float32)
    ramp = 0.3 * x * 10.0  # rises toward the east (30% grade at 10 m pixels), so its normal tilts west
    east_sun = render_dem(ramp, 10.0, 90.0, 45.0, shadows=False)
    west_sun = render_dem(ramp, 10.0, 270.0, 45.0, shadows=False)  # sun in the west: the slope faces it
    assert west_sun[100, 100] > east_sun[100, 100] * 1.3


def test_step_shadow_length_matches_geometry():
    # sun in the east at 10 deg: terrain east of a pixel shadows it, so the low ground just west of a cliff
    # that rises toward the east lies in shadow for height/tan(el) metres.
    h, w, px = 200, 400, 5.0
    dem = np.zeros((h, w), np.float32)
    dem[:, 250:] = 100.0
    shadow = cast_shadow_mask(dem, px, 90.0, 10.0)
    expected = 100.0 / np.tan(np.radians(10.0)) / px  # ~113.5 px
    row = shadow[h // 2]
    run = 0
    x = 249
    while x >= 0 and row[x]:
        run += 1
        x -= 1
    assert abs(run - expected) < 3
    assert not row[250:].any()


def test_shadow_direction_follows_azimuth():
    dem = np.zeros((300, 300), np.float32)
    dem[140:160, 140:160] = 80.0
    south = cast_shadow_mask(dem, 5.0, 0.0, 15.0)  # sun in the north -> shadow to the south (larger rows)
    ys, xs = np.nonzero(south)
    assert ys.mean() > 160 and abs(xs.mean() - 150) < 8
    north = cast_shadow_mask(dem, 5.0, 180.0, 15.0)
    ys, xs = np.nonzero(north)
    assert ys.mean() < 140


def test_sun_below_horizon_is_all_shadow():
    assert cast_shadow_mask(np.zeros((20, 20), np.float32), 5.0, 0.0, -1.0).all()
