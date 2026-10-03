"""Stage 5 (high-relief case) -- terrain-aware correction.

A rigorous DTM orthorectification would trace each pixel through the camera's own pointing model (RPCs / SPICE)
onto a DEM. The calibrated products do not ship that model, so the equivalent is done *empirically against
the reference*, which is itself orthorectified: `geometry.parallax` fits the DEM-driven look-angle
displacement (alpha * height, two coefficients, checked against the label's roll/pitch/camera tilt) and
`geometry.nonrigid` absorbs whatever the DEM does not explain (jitter, DEM error). `registration.register`
combines them, and `export.write_registered_geotiff` resamples the source through the result. This module
only re-exports that for callers that expect an "orthorectify" entry point.
"""

from algo.geometry.nonrigid import NonRigidModel  # noqa: F401
from algo.geometry.parallax import fit_parallax  # noqa: F401
from algo.registration import register as orthorectify_to_reference  # noqa: F401
