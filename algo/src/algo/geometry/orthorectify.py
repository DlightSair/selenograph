"""Stage 5 (high-relief case) — DTM-based orthorectification using a rigorous sensor model."""


def dtm_orthorectify(source_tile, reference_tile, dem, matches):
    """
    TODO:
    - Use the DEM + sensor pointing model (RPCs where available) to project matches
      through true 3D geometry instead of a flat 2D homography — needed near crater
      rims/walls where parallax between differing orbital viewpoints is significant.
    """
    raise NotImplementedError
