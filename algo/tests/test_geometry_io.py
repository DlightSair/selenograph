"""Source reading (decimation, destriping), label-corner geolocation and the exported GeoTIFF / tie points."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from algo.export import write_registered_geotiff, write_tiepoints_geo
from algo.geometry.nonrigid import NonRigidModel
from algo.matching.learned import Match
from algo.preprocessing.grid import decimation_for, decimation_matrix, load_geometry_grid, remove_column_stripes

REPO = Path(__file__).resolve().parents[2]


def test_destriping_removes_column_gain_but_keeps_broad_gradients():
    rng = np.random.default_rng(0)
    rows, cols = 400, 250
    terrain = 100 + 30 * np.linspace(0, 1, cols)[None, :] + rng.normal(0, 2, (rows, cols))  # slow cross-track brightness ramp
    gain = 1 + 0.08 * rng.normal(size=cols)
    striped = (terrain * gain[None, :]).astype(np.float32)
    clean = remove_column_stripes(striped)
    def stripe_level(img):  # high-frequency part of the column-median profile, interior columns only
        prof = np.median(img, axis=0)
        return float(np.std((prof - np.convolve(prof, np.ones(9) / 9, "same"))[10:-10]))

    col_std_before, col_std_after = stripe_level(striped), stripe_level(clean)
    assert col_std_after < 0.35 * col_std_before
    assert abs(clean[:, -20:].mean() - clean[:, :20].mean() - (terrain[:, -20:].mean() - terrain[:, :20].mean())) < 3.0  # ramp survives


def test_decimation_factor_and_matrix():
    assert decimation_for((0, 1000, 0, 1000)) == 1
    d = decimation_for((0, 100_000, 0, 12_000))  # an OHRC strip: 1.2 Gpx
    assert 4 <= d <= 8
    S = decimation_matrix((0, 100_000, 0, 12_000), (100_000 // d, 12_000 // d))
    assert abs(S[0, 0] - d) < 0.05 and abs(S[0, 2] - (0.5 * d - 0.5)) < 0.05


def test_registered_geotiff_is_georeferenced_and_shifted_like_the_model(tmp_path):
    src = np.zeros((120, 160), np.float32)
    src[60, 80] = 500.0
    H = np.array([[1.0, 0, 30.0], [0, 1.0, 20.0], [0, 0, 1.0]])
    model = NonRigidModel(H=H)
    ref_transform = from_origin(1000.0, 5000.0, 5.0, 5.0)
    path = tmp_path / "registered.tif"
    write_registered_geotiff(path, model, src, np.eye(3), (300, 300), ref_transform, "EPSG:32633", row_off=10, col_off=40)
    with rasterio.open(path) as ds:
        assert ds.crs.to_string() == "EPSG:32633"
        assert ds.transform.c == 1000.0 + 40 * 5.0 and ds.transform.f == 5000.0 - 10 * 5.0  # crop offset applied
        a = ds.read(1)
    y, x = np.unravel_index(np.argmax(a), a.shape)
    assert abs(x - (80 + 30)) <= 1 and abs(y - (60 + 20)) <= 1
    assert a[0, 0] == 0.0  # outside the source: nodata


def test_tiepoints_csv_has_geographic_columns(tmp_path):
    ref_transform = from_origin(0.0, 0.0, 100.0, 100.0)
    crs = "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=1737400 +units=m +no_defs"
    out = tmp_path / "tiepoints.csv"
    write_tiepoints_geo(out, [Match((10.0, 20.0), (1500.0, 2200.0), 0.8)], ref_transform, crs, (1000, 2000, 50, 100))
    row = next(csv.DictReader(open(out)))
    assert float(row["source_line"]) == pytest.approx(1020.0) and float(row["source_sample"]) == pytest.approx(60.0)
    assert -85.0 < float(row["lat_deg"]) < -78.0 and 0.0 <= float(row["lon_deg_e"]) < 360.0


@pytest.mark.skipif(not (REPO / "data/raw/chandrayaan2/tmc2/ch2_tmc_ncn_20260905T2337004268_d_img_d18").exists(), reason="needs the local TMC product")
def test_corner_geolocation_matches_the_real_control_grid_within_a_few_km():
    from algo.preprocessing.grid import corner_control_grid
    from algo.utils.io import find_pds4_product

    product = REPO / "data/raw/chandrayaan2/tmc2/ch2_tmc_ncn_20260905T2337004268_d_img_d18"
    real = load_geometry_grid(next((product / "geometry").rglob("*.csv")))
    syn = corner_control_grid(find_pds4_product(product)[1])
    lookup = {(int(l), int(s)): (la, lo) for l, s, la, lo in zip(syn.lines, syn.samples, syn.lats, syn.lons)}
    errs = []
    for l, s, la, lo in zip(real.lines, real.samples, real.lats, real.lons):
        if (int(l), int(s)) in lookup:
            la2, lo2 = lookup[(int(l), int(s))]
            errs.append(np.hypot(np.radians(la - la2), np.radians(lo - lo2) * np.cos(np.radians(la))) * 1_737_400)
    assert errs and np.median(errs) < 2000.0
