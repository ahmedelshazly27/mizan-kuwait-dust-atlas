import numpy as np

from kda import config as C
from kda import grid


def test_every_cell_gets_a_pixel():
    ny, nx = grid.shape()
    n = np.zeros(ny * nx, int)
    for t in C.MAIAC_TILES:
        np.add.at(n, grid.tile_mapping(t)[1], 1)
    assert n.min() >= 1


def test_tile_corner_matches_modis_grid():
    # Upper-left pixel centre of h22v06 is at 30 N minus half a pixel.
    lon, lat = grid.tile_lonlat("h22v06")
    assert abs(lat[0, 0] - (30 - 0.5 * grid.PIX_M / grid.R_EARTH * 180 / np.pi)) < 1e-6


def test_every_site_has_pixels():
    found = set()
    for t in C.MAIAC_TILES:
        found |= set(grid.site_pixels(t))
    assert found == set(C.AERONET_SITES)
