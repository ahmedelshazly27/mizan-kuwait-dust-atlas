"""The target grid, and the mapping from MODIS sinusoidal pixels onto it."""

from functools import lru_cache

import numpy as np

from . import config as C

# MODIS sinusoidal projection constants (MODIS Land grid definition).
R_EARTH = 6371007.181
TILE_M = 1111950.5197665554
NPIX_1KM = 1200
PIX_M = TILE_M / NPIX_1KM  # 926.625 m
X_ORIGIN = -20015109.354
Y_ORIGIN = 10007554.677


def target_axes():
    """Cell-centre longitudes (west to east) and latitudes (north to south)."""
    nx = round((C.LON_MAX - C.LON_MIN) / C.GRID_RES)
    ny = round((C.LAT_MAX - C.LAT_MIN) / C.GRID_RES)
    lon = C.LON_MIN + (np.arange(nx) + 0.5) * C.GRID_RES
    lat = C.LAT_MAX - (np.arange(ny) + 0.5) * C.GRID_RES
    return np.round(lon, 6), np.round(lat, 6)


def shape():
    lon, lat = target_axes()
    return lat.size, lon.size


def tile_lonlat(tile):
    """Lon/lat of every 1 km pixel centre in a tile like 'h22v06'."""
    h, v = int(tile[1:3]), int(tile[4:6])
    j = np.arange(NPIX_1KM) + 0.5
    x = X_ORIGIN + h * TILE_M + j * PIX_M
    y = Y_ORIGIN - v * TILE_M - j * PIX_M
    xx, yy = np.meshgrid(x, y)
    lat = np.degrees(yy / R_EARTH)
    lon = np.degrees(xx / (R_EARTH * np.cos(np.radians(lat))))
    return lon, lat


@lru_cache(maxsize=None)
def tile_mapping(tile):
    """Source pixels that fall in the domain, and the target cell each lands in.

    Returns (src_flat_index, tgt_flat_index). Each target cell averages the
    sinusoidal pixels whose centres fall inside it (bin averaging). At 0.01 deg
    and 0.93 km source pixels that is one to three pixels; over this domain no
    target cell is left without a pixel (checked in tests/test_grid.py).
    """
    lon, lat = tile_lonlat(tile)
    ny, nx = shape()
    col = np.floor((lon - C.LON_MIN) / C.GRID_RES).astype(int)
    row = np.floor((C.LAT_MAX - lat) / C.GRID_RES).astype(int)
    ok = (col >= 0) & (col < nx) & (row >= 0) & (row < ny)
    src = np.flatnonzero(ok)
    tgt = row.ravel()[src] * nx + col.ravel()[src]
    return src, tgt


def haversine_km(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


@lru_cache(maxsize=None)
def site_pixels(tile):
    """Per AERONET site, the flat indices of tile pixels within MATCH_RADIUS_KM."""
    lon, lat = tile_lonlat(tile)
    out = {}
    for site, (slon, slat) in C.AERONET_SITES.items():
        d = haversine_km(lon, lat, slon, slat)
        idx = np.flatnonzero(d.ravel() <= C.MATCH_RADIUS_KM)
        if idx.size:
            out[site] = idx
    return out
