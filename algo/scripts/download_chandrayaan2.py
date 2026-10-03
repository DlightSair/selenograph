"""
Helper to organize Chandrayaan-2 downloads from ISSDC chmapbrowse into data/raw/chandrayaan2/.

ISSDC chmapbrowse (https://chmapbrowse.issdc.gov.in/MapBrowse/) doesn't expose a public
bulk-download API — downloads happen through its query form (instrument, PDS product type,
AOI lat/lon box, optional date range). This script is a placeholder for organizing whatever
gets manually downloaded from there into a consistent local layout:

  data/raw/chandrayaan2/<instrument>/<product_type>/<product_id>/

Not implemented: ISSDC downloads are performed manually.
"""

if __name__ == "__main__":
    raise NotImplementedError("See module docstring — ISSDC downloads are manual via chmapbrowse.")
