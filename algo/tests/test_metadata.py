"""Stage 0 tests against the real TMC-2 DTM product in data/dem/tycho/."""

from pathlib import Path

import pytest

from algo.preprocessing.metadata import load_reference_metadata, parse_pds4_label
from algo.utils.io import find_pds4_product

DTM_PRODUCT = (
    Path(__file__).parents[2]
    / "data"
    / "dem"
    / "tycho"
    / "ch2_tmc_ndn_20240124T0838058678_d_dtm_d18"
)

pytestmark = pytest.mark.skipif(not DTM_PRODUCT.exists(), reason="sample DTM product not present")


def test_find_pds4_product():
    data_path, label_path = find_pds4_product(DTM_PRODUCT)
    assert data_path.suffix == ".tif"
    assert label_path.suffix == ".xml"


def test_parse_pds4_label():
    _data_path, label_path = find_pds4_product(DTM_PRODUCT)
    meta = parse_pds4_label(label_path)

    assert meta.sun_azimuth == pytest.approx(43.162789, abs=1e-3)
    assert meta.sun_elevation == pytest.approx(39.378707, abs=1e-3)
    assert meta.shape == (100103, 6753)
    assert len(meta.footprint) == 4
    # Tycho crater (43.3S, 11.36W == 348.64E) must fall inside this product's footprint.
    lats = [lat for lat, _lon in meta.footprint]
    lons = [lon for _lat, lon in meta.footprint]
    assert min(lats) <= -43.3 <= max(lats)
    assert min(lons) <= 348.64 <= max(lons)
    # Label states 10 m/px.
    assert meta.gsd == pytest.approx(10.0, rel=0.1)


def test_load_reference_metadata_reads_the_dtm_raster_itself():
    data_path, _label_path = find_pds4_product(DTM_PRODUCT)
    meta = load_reference_metadata(data_path)

    assert meta.shape == (100103, 6753)
    assert meta.gsd == pytest.approx(10.0, rel=0.1)


def test_read_raster_header_matches_label(tmp_path):
    data_path, _label_path = find_pds4_product(DTM_PRODUCT)
    # Read a single row instead of the full 1.3GB band for a fast smoke test.
    import rasterio

    with rasterio.open(data_path) as ds:
        assert ds.width == 6753
        assert ds.height == 100103
        assert ds.dtypes[0] == "int16"
