"""Shared raster/label IO helpers used across stages."""


def read_raster(path):
    """TODO: load a georeferenced raster (rasterio) — Chandrayaan-2 PDS product or LRO WAC/NAC tile."""
    raise NotImplementedError


def write_raster(path, array, transform, crs):
    """TODO: write a georeferenced output raster (registered source image) via rasterio."""
    raise NotImplementedError
