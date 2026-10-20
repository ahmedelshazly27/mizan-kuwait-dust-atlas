"""MERRA-2 monthly aerosol diagnostics (M2TMNXAER), for comparison with MAIAC.

Used only to choose the AOD source; not part of the published grids. Each
global monthly file (~84 MB) is cut to the Kuwait box and deleted. Needs
EARTHDATA_TOKEN and the GES DISC application approved on that account.
"""

import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import xarray as xr

from . import config as C
from . import http

BASE = "https://goldsmr4.gesdisc.eosdis.nasa.gov/data/MERRA2_MONTHLY/M2TMNXAER.5.12.4"
OUT = C.INTERIM / "merra2_kuwait_monthly.nc"
VARS = ["TOTEXTTAU", "DUEXTTAU"]
BOX = dict(lat=slice(27.5, 31.0), lon=slice(45.5, 49.5))
# The netCDF/HDF5 library is not thread-safe: worker threads only download;
# every read and write happens in the main thread.


def _session():
    return http.session()


def _files(session):
    out = []
    for y in range(int(C.START[:4]), date.today().year + 1):
        r = session.get(f"{BASE}/{y}/", timeout=120)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        out += [(y, n) for n in sorted(set(re.findall(r"MERRA2_\d+\.tavgM_2d_aer_Nx\.\d{6}\.nc4", r.text)))]
    return out


def _download(session, y, name, tmp):
    p = Path(tmp) / name
    for attempt in range(4):
        try:
            r = session.get(f"{BASE}/{y}/{name}", timeout=600)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 3:
                raise
    p.write_bytes(r.content)
    return p


def _subset(p):
    try:
        with xr.open_dataset(p) as d:
            return d[VARS].sel(**BOX).load()
    finally:
        p.unlink(missing_ok=True)


def run(workers=4):
    """Fetch every month not already in OUT, saving as it goes."""
    from concurrent.futures import as_completed

    s = _session()
    parts = [xr.open_dataset(OUT).load()] if OUT.exists() else []
    done = set(pd.to_datetime(parts[0].time.values).strftime("%Y%m")) if parts else set()
    todo = [(y, n) for y, n in _files(s) if n[-10:-4] not in done]
    print(f"MERRA-2: {len(todo)} months to fetch", flush=True)

    def save():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix(".tmp.nc")
        xr.concat(parts, "time").sortby("time").to_netcdf(tmp)
        tmp.replace(OUT)

    with tempfile.TemporaryDirectory(dir=C.RAW) as tmp, ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(_download, s, y, n, tmp) for y, n in todo]
        for k, fu in enumerate(as_completed(futs), 1):
            try:
                parts.append(_subset(fu.result()))
            except Exception as e:  # logged; fetched again on the next run
                print(f"  FAILED month: {e!r}"[:300], flush=True)
            if k % 20 == 0 or k == len(futs):
                save()
                print(f"  {k}/{len(futs)}", flush=True)
    return xr.open_dataset(OUT)


def at_sites(ds=None):
    """Monthly total AOD at the MERRA-2 cell containing each AERONET site."""
    ds = ds if ds is not None else xr.open_dataset(OUT)
    out = {}
    for site, (lon, lat) in C.AERONET_SITES.items():
        v = ds.TOTEXTTAU.sel(lat=lat, lon=lon, method="nearest").to_series()
        v.index = pd.to_datetime(v.index).to_period("M")
        out[site] = v
    return out


def cells_over_kuwait(ds=None):
    """How many MERRA-2 cells have their centre inside the study box."""
    ds = ds if ds is not None else xr.open_dataset(OUT)
    lat, lon = ds.lat.values, ds.lon.values
    return int(((lat >= C.LAT_MIN) & (lat <= C.LAT_MAX)).sum() * ((lon >= C.LON_MIN) & (lon <= C.LON_MAX)).sum())
