"""MODIS MAIAC MCD19A2 C6.1: find, download, cut to Kuwait, discard.

Discovery uses the public LAADS archive listing (no login, and independent of
NASA's CMR search). Files are downloaded from the LP DAAC cloud archive with an
Earthdata token (EARTHDATA_TOKEN). Each file is reduced to two things before it
is deleted:

1. A daily grid on the 0.01 degree target grid: mean of every best-quality
   retrieval (all Terra and Aqua overpasses) whose pixel centre falls in the cell.
2. Per AERONET site and per overpass: statistics of the best-quality pixels
   within MATCH_RADIUS_KM, with the overpass time, for validation.
"""

import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
from pyhdf.SD import SD, SDC

from . import config as C
from . import grid

LAADS = "https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MCD19A2"
LPCLOUD = "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/MCD19A2.061"
FILL = -28672
SCALE = 0.001

# The HDF4 library is not thread-safe: downloads run in parallel, reads one at a time.
_READ = threading.Lock()

INDEX = C.RAW / "maiac_index.json"
DAILY = C.INTERIM / "maiac_daily"
SITES = C.INTERIM / "maiac_sites"


def best_quality(qa):
    """Cloud mask 'clear' (bits 0-2 = 001) and adjacency mask 'normal' (bits 5-7 = 000)."""
    return ((qa & 0b111) == 1) & (((qa >> 5) & 0b111) == 0)


def parse_orbits(stamp):
    """'20251800545T  20251800720T  20251801055A' -> [(datetime UTC, 'T'), ...]"""
    out = []
    for tok in stamp.split():
        t = datetime.strptime(tok[:11], "%Y%j%H%M")
        out.append((t, tok[11]))
    return out


# ---------------------------------------------------------------- discovery


def _list(url):
    r = requests.get(url + ".json", timeout=120)
    r.raise_for_status()
    d = r.json()
    return d.get("content", d) if isinstance(d, dict) else d


def build_index(end=None, refresh=False):
    """{'YYYY-MM-DD': {'h22v05': filename, 'h22v06': filename}} for every day."""
    idx = json.loads(INDEX.read_text()) if INDEX.exists() and not refresh else {}
    end = end or date.today()
    d0 = date.fromisoformat(C.START)
    todo = [d0 + timedelta(n) for n in range((end - d0).days + 1) if (d0 + timedelta(n)).isoformat() not in idx]

    def one(d):
        try:
            names = [x["name"] for x in _list(f"{LAADS}/{d.year}/{d.timetuple().tm_yday:03d}")]
        except requests.HTTPError:
            return d, None  # day not processed yet
        return d, {t: n for n in names for t in C.MAIAC_TILES if f".{t}." in n}

    INDEX.parent.mkdir(parents=True, exist_ok=True)

    def save():
        INDEX.write_text(json.dumps(dict(sorted(idx.items())), indent=0))

    print(f"MAIAC index: {len(todo)} days to list", flush=True)
    with ThreadPoolExecutor(16) as ex:
        for k, (d, files) in enumerate(ex.map(one, todo), 1):
            if files is not None and len(files) == len(C.MAIAC_TILES):
                idx[d.isoformat()] = files
            if k % 250 == 0:
                save()
                print(f"  index {k}/{len(todo)}", flush=True)
    save()
    return idx


# ---------------------------------------------------------------- per file


def _session():
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + os.environ["EARTHDATA_TOKEN"].strip()
    return s


def _download(session, name, dest):
    stem = name[:-4]
    url = f"{LPCLOUD}/{stem}/{name}"
    # The archive redirects to a signed S3 URL; requests drops the Authorization
    # header on the cross-host redirect, which is what S3 wants.
    for attempt in range(4):
        try:
            r = session.get(url, timeout=600)
            r.raise_for_status()
            if r.content[:4] != b"\x0e\x03\x13\x01":
                raise OSError(f"not an HDF4 file: {name}")
            dest.write_bytes(r.content)
            return dest
        except (requests.RequestException, OSError):
            if attempt == 3:
                raise


def reduce_file(path, tile):
    """One tile-day -> (sum, count) on the target grid, and per-site overpass rows."""
    with _READ:
        f = SD(str(path), SDC.READ)
        aod = f.select("Optical_Depth_055")[:].astype(np.float32)
        qa = f.select("AOD_QA")[:]
        orbits = parse_orbits(f.attributes()["Orbit_time_stamp"])
        f.end()

    ok = best_quality(qa) & (aod != FILL)
    aod = np.where(ok, aod * SCALE, np.nan)

    src, tgt = grid.tile_mapping(tile)
    ny, nx = grid.shape()
    flat = aod.reshape(aod.shape[0], -1)[:, src]
    good = np.isfinite(flat)
    s = np.zeros(ny * nx)
    n = np.zeros(ny * nx)
    for o in range(flat.shape[0]):
        np.add.at(s, tgt[good[o]], flat[o, good[o]])
        np.add.at(n, tgt[good[o]], 1)

    rows = []
    for site, pix in grid.site_pixels(tile).items():
        for o, (t, sat) in enumerate(orbits):
            v = aod[o].ravel()[pix]
            v = v[np.isfinite(v)]
            rows.append(
                dict(site=site, time=t, sat=sat, n=v.size, n_in_radius=pix.size,
                     aod_mean=float(v.mean()) if v.size else np.nan,
                     aod_median=float(np.median(v)) if v.size else np.nan,
                     aod_std=float(v.std()) if v.size > 1 else np.nan)
            )
    return s, n, rows


def process_day(session, day, files, tmpdir):
    ny, nx = grid.shape()
    s = np.zeros(ny * nx)
    n = np.zeros(ny * nx)
    rows = []
    for tile, name in files.items():
        p = _download(session, name, tmpdir / name)
        try:
            ts, tn, tr = reduce_file(p, tile)
        finally:
            p.unlink(missing_ok=True)
        s += ts
        n += tn
        rows += tr
    with np.errstate(invalid="ignore"):
        daily = np.where(n > 0, s / n, np.nan).reshape(ny, nx).astype(np.float32)
    return day, daily, n.reshape(ny, nx).astype(np.uint8), rows


# ---------------------------------------------------------------- driver


def run(workers=6, end=None):
    """Process every indexed day not already done, one year file at a time."""
    from pathlib import Path

    idx = build_index(end)
    DAILY.mkdir(parents=True, exist_ok=True)
    SITES.mkdir(parents=True, exist_ok=True)
    session = _session()
    years = sorted({d[:4] for d in idx})
    for y in years:
        days = sorted(d for d in idx if d.startswith(y))
        out = DAILY / f"maiac_daily_{y}.npz"
        done = {}
        if out.exists():
            z = np.load(out)
            done = {d: (z["aod"][i], z["n"][i]) for i, d in enumerate(z["dates"])}
            if set(days) <= set(done):
                continue
        site_rows = []
        sp = SITES / f"maiac_sites_{y}.parquet"
        if sp.exists():
            site_rows = pd.read_parquet(sp).to_dict("records")
        todo = [d for d in days if d not in done]
        print(f"MAIAC {y}: {len(todo)} days to process", flush=True)
        with tempfile.TemporaryDirectory(dir=C.RAW) as tmp, ThreadPoolExecutor(workers) as ex:
            futs = [ex.submit(process_day, session, d, idx[d], Path(tmp)) for d in todo]
            for k, fu in enumerate(as_completed(futs), 1):
                try:
                    d, daily, n, rows = fu.result()
                except Exception as e:  # logged; the day is retried on the next run
                    print(f"  FAILED day: {e!r}"[:300], flush=True)
                    continue
                done[d] = (daily, n)
                site_rows += rows
                if k % 50 == 0 or k == len(futs):
                    _save_year(out, done)
                    pd.DataFrame(site_rows).to_parquet(sp)
                    print(f"  {y}: {k}/{len(futs)}", flush=True)
        _save_year(out, done)
        pd.DataFrame(site_rows).to_parquet(sp)


def _save_year(path, done):
    ds = sorted(done)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, dates=np.array(ds), aod=np.stack([done[d][0] for d in ds]), n=np.stack([done[d][1] for d in ds]))
    tmp.rename(path)


def load_daily():
    """All daily grids as an xarray DataArray (time, lat, lon) of AOD 550 nm."""
    import xarray as xr

    lon, lat = grid.target_axes()
    parts = []
    for p in sorted(DAILY.glob("maiac_daily_*.npz")):
        z = np.load(p)
        parts.append(xr.DataArray(z["aod"], dims=("time", "lat", "lon"),
                                  coords=dict(time=pd.to_datetime(z["dates"]), lat=lat, lon=lon)))
    return xr.concat(parts, "time").sortby("time").rename("aod550")


def load_sites():
    return pd.concat([pd.read_parquet(p) for p in sorted(SITES.glob("*.parquet"))], ignore_index=True)
