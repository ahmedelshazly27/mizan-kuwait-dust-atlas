"""Sentinel-5P TROPOMI UV aerosol index (354/388 nm), as an independent cross-check.

The aerosol index responds to UV-absorbing aerosol (dust, smoke) and is
qualitative: it depends on aerosol height as well as amount, and it is not AOD.
So it is compared with MAIAC by correlation only, never by value.

Files are cut to the study box on NASA's side by Harmony (one job per month),
so only Kuwait pixels are downloaded. Needs EARTHDATA_TOKEN, and the Copernicus
Sentinel data licence accepted on that Earthdata account.
"""

import re
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import config as C
from . import http

HARMONY = "https://harmony.earthdata.nasa.gov"
COLLECTION = "C2087131083-GES_DISC"  # S5P_L2__AER_AI_HiR version 2
START = "2018-05-01"  # first full month of the record
QA_MIN = 0.8  # product user manual recommendation for the aerosol index
RES = 0.1  # TROPOMI pixels are 3.5 x 5.5 km; a 0.1 degree grid is about right
OUT = C.INTERIM / "s5p_aai_monthly_0p1.nc"
_READ = threading.Lock()


def axes():
    lon = np.arange(C.LON_MIN + RES / 2, C.LON_MAX, RES).round(4)
    lat = np.arange(C.LAT_MAX - RES / 2, C.LAT_MIN, -RES).round(4)
    return lon, lat


def _session():
    return http.session()


def _submit(s, t0, t1):
    url = f"{HARMONY}/{COLLECTION}/ogc-api-coverages/1.0.0/collections/parameter_vars/coverage/rangeset"
    params = [
        ("variable", "PRODUCT/aerosol_index_354_388"),
        ("variable", "PRODUCT/qa_value"),
        ("subset", f"lat({C.LAT_MIN}:{C.LAT_MAX})"),
        ("subset", f"lon({C.LON_MIN}:{C.LON_MAX})"),
        ("subset", f'time("{t0}":"{t1}")'),
        ("forceAsync", "true"),
    ]
    r = s.get(url, params=params, timeout=300)
    r.raise_for_status()
    return r.json()


def _wait(s, job):
    while job["status"] in ("accepted", "running", "running_with_errors"):
        time.sleep(20)
        job = s.get(f"{HARMONY}/jobs/{job['jobID']}", timeout=120).json()
    return job


def _grid_file(path, sums, counts, day_index):
    with _READ, xr.open_dataset(path, group="PRODUCT") as d:
        ai = d["aerosol_index_354_388"].values.squeeze()
        qa = d["qa_value"].values.squeeze()
        lat = d["latitude"].values.squeeze()
        lon = d["longitude"].values.squeeze()
    ok = np.isfinite(ai) & (qa >= QA_MIN)
    col = np.floor((lon[ok] - C.LON_MIN) / RES).astype(int)
    row = np.floor((C.LAT_MAX - lat[ok]) / RES).astype(int)
    lonax, latax = axes()
    inside = (col >= 0) & (col < lonax.size) & (row >= 0) & (row < latax.size)
    np.add.at(sums[day_index], (row[inside], col[inside]), ai[ok][inside])
    np.add.at(counts[day_index], (row[inside], col[inside]), 1)


def month(s, m):
    """Monthly mean of daily-mean aerosol index on the 0.1 degree grid."""
    t0 = pd.Timestamp(m)
    t1 = t0 + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    job = _wait(s, _submit(s, t0.strftime("%Y-%m-%dT%H:%M:%SZ"), t1.strftime("%Y-%m-%dT%H:%M:%SZ")))
    if job["status"] not in ("successful", "complete_with_errors"):
        raise RuntimeError(f"Harmony job {job['jobID']} {job['status']}: {job.get('message')}")
    lonax, latax = axes()
    nd = t1.day
    sums = np.zeros((nd, latax.size, lonax.size))
    counts = np.zeros_like(sums)
    links = [l["href"] for l in job.get("links", []) if l.get("rel") == "data"]
    with tempfile.TemporaryDirectory(dir=C.RAW) as tmp:
        for href in links:
            name = href.rsplit("/", 1)[-1]
            p = Path(tmp) / name
            p.write_bytes(s.get(href, timeout=600).content)
            # Orbit start time follows the product name: ..._L2__AER_AI_YYYYMMDDTHHMMSS_...
            day = int(re.search(r"AER_AI_(\d{8})T", name).group(1)[6:8])
            _grid_file(p, sums, counts, day - 1)
            p.unlink()
    with np.errstate(invalid="ignore"):
        daily = np.where(counts > 0, sums / counts, np.nan)
        ndays = np.isfinite(daily).sum(0)
        mean = np.where(ndays >= C.MIN_DAYS_PER_MONTH, np.nanmean(daily, 0), np.nan)
    return xr.Dataset(
        dict(aai=(("lat", "lon"), mean.astype("float32")), n_days=(("lat", "lon"), ndays.astype("int16"))),
        coords=dict(lat=latax, lon=lonax),
    ).expand_dims(time=[t0])


def run(end=None):
    s = _session()
    parts = [xr.open_dataset(OUT).load()] if OUT.exists() else []
    done = set(pd.to_datetime(parts[0].time.values)) if parts else set()
    last = (pd.Timestamp(end) if end else pd.Timestamp.today()).normalize() - pd.offsets.MonthBegin(1)
    todo = [m for m in pd.date_range(START, last, freq="MS") if m not in done]
    print(f"S5P: {len(todo)} months to fetch", flush=True)
    for k, m in enumerate(todo, 1):
        try:
            parts.append(month(s, m))
        except Exception as e:  # logged; fetched again on the next run
            print(f"  FAILED {m:%Y-%m}: {e!r}"[:300], flush=True)
            continue
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT.with_suffix(".tmp.nc")
        xr.concat(parts, "time").sortby("time").to_netcdf(tmp)
        tmp.replace(OUT)
        print(f"  {m:%Y-%m} done ({k}/{len(todo)})", flush=True)
    return xr.open_dataset(OUT)
