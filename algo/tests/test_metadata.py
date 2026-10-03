"""Metadata tests against real PDS4 products: a TMC-2 DTM (data/dem/tycho/), an
OHRC image and a TMC-2 image with polar footprints (confirming that the label
parser generalizes across instruments with no instrument-specific code), and the
TMC-2 Calibrated image from the same orbit (19674) as the Tycho DTM."""

from pathlib import Path

import pytest

from algo.preprocessing.metadata import load_reference_metadata, parse_pds4_label
from algo.utils.io import find_pds4_product

DATA_ROOT = Path(__file__).parents[2] / "data"
DTM_PRODUCT = DATA_ROOT / "dem" / "tycho" / "ch2_tmc_ndn_20240124T0838058678_d_dtm_d18"
OHRC_PRODUCT = DATA_ROOT / "raw" / "chandrayaan2" / "ohrc" / "ch2_ohr_ncp_20241115T1525004388_d_img_d18"
TMC2_NORTH_PRODUCT = DATA_ROOT / "raw" / "chandrayaan2" / "tmc2" / "ch2_tmc_ncf_20230127T1218474820_d_img_d32"
TMC2_TYCHO_PRODUCT = DATA_ROOT / "raw" / "chandrayaan2" / "tmc2" / "ch2_tmc_ncn_20240124T0838058678_d_img_d18"

skip_without_dtm = pytest.mark.skipif(not DTM_PRODUCT.exists(), reason="sample DTM product not present")
skip_without_ohrc = pytest.mark.skipif(not OHRC_PRODUCT.exists(), reason="sample OHRC product not present")
skip_without_tmc2_north = pytest.mark.skipif(
    not TMC2_NORTH_PRODUCT.exists(), reason="sample North Pole TMC-2 product not present"
)
skip_without_tmc2_tycho = pytest.mark.skipif(
    not TMC2_TYCHO_PRODUCT.exists(), reason="Tycho-matching TMC-2 source product not present"
)


@skip_without_dtm
def test_find_pds4_product():
    data_path, label_path = find_pds4_product(DTM_PRODUCT)
    assert data_path.suffix == ".tif"
    assert label_path.suffix == ".xml"


@skip_without_dtm
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


@skip_without_dtm
def test_load_reference_metadata_reads_the_dtm_raster_itself():
    data_path, _label_path = find_pds4_product(DTM_PRODUCT)
    meta = load_reference_metadata(data_path)

    assert meta.shape == (100103, 6753)
    assert meta.gsd == pytest.approx(10.0, rel=0.1)


@skip_without_dtm
def test_read_raster_header_matches_label():
    data_path, _label_path = find_pds4_product(DTM_PRODUCT)
    # Read header only, not the full 1.3GB band, for a fast smoke test.
    import rasterio

    with rasterio.open(data_path) as ds:
        assert ds.width == 6753
        assert ds.height == 100103
        assert ds.dtypes[0] == "int16"


@skip_without_ohrc
def test_parse_pds4_label_on_ohrc_product():
    """A second, structurally different instrument product (Calibrated OHRC,
    South Pole footprint) to confirm parse_pds4_label isn't DTM-specific."""
    _data_path, label_path = find_pds4_product(OHRC_PRODUCT)
    meta = parse_pds4_label(label_path)

    assert meta.sun_azimuth == pytest.approx(242.980602, abs=1e-3)
    assert meta.sun_elevation == pytest.approx(0.785661, abs=1e-3)
    assert meta.shape == (101074, 12000)
    # Label states 0.24 m/px; the great-circle estimate is rough near the pole
    # (longitude degenerates there) so allow a looser tolerance than the DTM case.
    assert meta.gsd == pytest.approx(0.24, rel=0.2)


@skip_without_tmc2_north
def test_parse_pds4_label_on_tmc2_product():
    """A third real product (Calibrated TMC-2, North Pole footprint) -- same
    parser, no instrument-specific branches needed."""
    _data_path, label_path = find_pds4_product(TMC2_NORTH_PRODUCT)
    meta = parse_pds4_label(label_path)

    assert meta.sun_azimuth == pytest.approx(144.281139, abs=1e-3)
    assert meta.sun_elevation == pytest.approx(11.540438, abs=1e-3)
    assert meta.shape == (185749, 4000)
    assert meta.gsd == pytest.approx(6.16, rel=0.2)


@skip_without_tmc2_tycho
def test_tmc2_tycho_product_matches_the_dtm_orbit_and_covers_tycho():
    """The TMC-2 source image: same orbit (19674) and sun angle as the Tycho
    DTM, and its footprint must actually contain Tycho crater."""
    _data_path, label_path = find_pds4_product(TMC2_TYCHO_PRODUCT)
    meta = parse_pds4_label(label_path)

    assert meta.sun_azimuth == pytest.approx(43.162789, abs=1e-3)
    assert meta.sun_elevation == pytest.approx(39.378707, abs=1e-3)
    lats = [lat for lat, _lon in meta.footprint]
    lons = [lon for _lat, lon in meta.footprint]
    assert min(lats) <= -43.3 <= max(lats)
    assert min(lons) <= 348.64 <= max(lons)
