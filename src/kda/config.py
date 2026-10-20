"""Every fixed choice the pipeline makes, in one place.

Change a value here and rerun; nothing else in the code hard-codes these.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"  # upstream files, never published by us
INTERIM = DATA / "interim"  # daily grids, match-ups
OUT = DATA / "out"  # the published dataset
WEB = DATA / "web"  # small files for the website

# Target grid: regular lat/lon, 0.01 degree (about 1.0 km E-W, 1.1 km N-S at 29 N).
# Edges, not centres. Covers mainland Kuwait, Bubiyan and Failaka.
GRID_RES = 0.01
LON_MIN, LON_MAX = 46.50, 48.50
LAT_MIN, LAT_MAX = 28.50, 30.15

# Period. The time series runs from START to the last complete month available.
# The climatology uses complete years only, so every calendar month has the same
# number of years behind it.
START = "2015-01-01"
CLIM_YEARS = (2015, 2025)

# A monthly mean needs at least this many valid days at a cell, otherwise NaN.
MIN_DAYS_PER_MONTH = 5

# AERONET sites in Kuwait (from aeronet_locations_v3.txt). Shagaya_Park is the
# primary validation site; the others are reported as supplementary.
AERONET_SITES = {
    "Shagaya_Park": (47.060528, 29.209072),
    "Kuwait_University": (47.971000, 29.325000),
    "Kuwait_University_2": (47.897000, 29.257600),
    "Kuwait_Airport": (47.972000, 29.242000),
    "Kuwait_Inst_Sci_Res": (47.906453, 29.337914),
}
PRIMARY_SITE = "Shagaya_Park"

# Match-up rules for satellite vs AERONET.
MATCH_RADIUS_KM = 5.0  # satellite pixels within this distance of the station
MATCH_WINDOW_MIN = 30  # AERONET observations within +/- this of the overpass
MATCH_MIN_PIXELS = 3  # need at least this many valid pixels in the radius

# MODIS sinusoidal tiles covering the domain.
MAIAC_TILES = ("h22v05", "h22v06")
