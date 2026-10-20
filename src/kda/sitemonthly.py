"""Satellite monthly means at each AERONET site, built the same way as the map.

Daily value = mean of all best-quality overpass means within the radius that
day; monthly value = mean of daily values, needing MIN_DAYS_PER_MONTH days.
"""

import pandas as pd

from . import config as C


def from_sites(sites):
    s = sites[sites.n >= C.MATCH_MIN_PIXELS].copy()
    s["day"] = pd.to_datetime(s.time).dt.floor("D")
    out = {}
    for site, g in s.groupby("site"):
        day = g.groupby("day").aod_mean.mean()
        nd = day.groupby(day.index.to_period("M")).size()
        mon = day.groupby(day.index.to_period("M")).mean()
        out[site] = mon[nd >= C.MIN_DAYS_PER_MONTH]
    return out
