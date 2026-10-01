"""Stage 1 — collapse illumination (sun angle) variation before matching."""


def normalize_illumination(source_cfg, reference_cfg, source_meta, reference_meta, dem_cfg):
    """
    TODO:
    - If dem_cfg['enabled']: load a DEM (SLDEM2015/LOLA, or a TMC-2-derived DTM) covering
      the AOI and re-render one image's surface under the other's sun azimuth/elevation
      (Lambertian or Lunar-Lambert hillshade) so both images are compared under a
      physically consistent illumination.
    - Else: fall back to a phase-congruency structure map (log-Gabor filter bank) for
      both images as an illumination- and modality-robust common representation.

    Returns (source_normalized, reference_normalized).
    """
    raise NotImplementedError
