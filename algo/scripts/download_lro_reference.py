"""
Helper to organize LRO reference imagery from QuickMap into data/raw/lro_reference/.

Workflow (manual, via https://quickmap.lroc.im-ldi.com):
  1. Navigate to the AOI (search box, or lat/lon).
  2. Ensure the desired layer is active (default WAC+NAC+NAC_ROI_MOSAIC, or add a specific
     NAC/NAC Regional Mosaic product via Object Inspector -> Products tab).
  3. Settings (gear icon) -> Export Image -> "Download PNG+VRT" to export the current
     view as a georeferenced PNG + .vrt pair.

This script is a placeholder for organizing whatever gets exported from there into:

  data/raw/lro_reference/<aoi_name>/<layer>/

TODO: fill in once the manual export step is done, or if QuickMap exposes a bulk API.
"""

if __name__ == "__main__":
    raise NotImplementedError("See module docstring — QuickMap exports are manual for now.")
