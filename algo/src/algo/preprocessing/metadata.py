"""Stage 0 — parse PDS labels for sun az/el, GSD, footprint; estimate scale ratio & rotation."""


def load_metadata(source_cfg: dict, reference_cfg: dict):
    """
    TODO:
    - Parse PDS3/4 labels (.lbl/.xml) alongside the source (OHRC/TMC-2/IIRS) and
      reference (LRO NAC/WAC) rasters for: sun azimuth, sun elevation, GSD,
      footprint corners (lat/lon), spacecraft orbital geometry.
    - Derive expected scale ratio (source GSD / reference GSD) and rough rotation
      (footprint corners vs. North) to narrow the search space before Stage 2.
    """
    raise NotImplementedError


class ImageMetadata:
    def __init__(self, sun_azimuth, sun_elevation, gsd, footprint):
        self.sun_azimuth = sun_azimuth
        self.sun_elevation = sun_elevation
        self.gsd = gsd
        self.footprint = footprint
