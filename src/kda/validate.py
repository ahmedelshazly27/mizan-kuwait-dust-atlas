"""Validation of satellite AOD against AERONET Level 2.0.

Two levels, because the published product is monthly but the satellite is
judged best per overpass:

1. Overpass match-ups. Satellite: mean of best-quality pixels within
   MATCH_RADIUS_KM, at least MATCH_MIN_PIXELS. Station: mean of observations
   within +/- MATCH_WINDOW_MIN of the overpass, at least 2.
2. Monthly means at the station: what a map user actually sees, compared with
   the station's own monthly mean of daily means.

Plus a retrieval-availability check: on days the station saw heavy dust, how
often did the satellite return nothing (heavy dust mistaken for cloud)?
"""

import json

import numpy as np
import pandas as pd

from . import config as C

WAVES = (500, 675)


def read_aeronet(site):
    """One row per observation: time (UTC) and AOD at 550 nm."""
    p = C.RAW / "aeronet" / f"{site}_L20_all.csv"
    with open(p) as f:
        head = next((i for i, line in enumerate(f) if line.startswith("AERONET_Site,")), None)
    if head is None:  # site has no Level 2.0 data
        return pd.DataFrame(columns=["time", "aod550"])
    d = pd.read_csv(p, skiprows=head, usecols=["Date(dd:mm:yyyy)", "Time(hh:mm:ss)", "AOD_500nm", "AOD_675nm"], na_values=[-999.0])
    if d.empty:
        return pd.DataFrame(columns=["time", "aod550"])
    d["time"] = pd.to_datetime(d["Date(dd:mm:yyyy)"] + " " + d["Time(hh:mm:ss)"], format="%d:%m:%Y %H:%M:%S")
    d = d.dropna(subset=["AOD_500nm", "AOD_675nm"])
    d = d[(d.AOD_500nm > 0) & (d.AOD_675nm > 0)]
    # Angstrom interpolation between the two channels that bracket 550 nm.
    alpha = -np.log(d.AOD_500nm / d.AOD_675nm) / np.log(WAVES[0] / WAVES[1])
    d["aod550"] = d.AOD_500nm * (550 / WAVES[0]) ** (-alpha)
    return d[["time", "aod550"]].reset_index(drop=True)


def stats(sat, ref):
    sat, ref = np.asarray(sat, float), np.asarray(ref, float)
    n = sat.size
    if n < 3:
        return dict(n=n)
    err = sat - ref
    ee = 0.05 + 0.15 * ref
    slope, intercept = np.polyfit(ref, sat, 1)
    return dict(
        n=int(n),
        r=float(np.corrcoef(sat, ref)[0, 1]),
        bias=float(err.mean()),
        rmse=float(np.sqrt((err**2).mean())),
        mae=float(np.abs(err).mean()),
        within_ee=float((np.abs(err) <= ee).mean()),
        slope=float(slope),
        intercept=float(intercept),
        ref_mean=float(ref.mean()),
        sat_mean=float(sat.mean()),
    )


def matchups(sat_sites, site):
    """Overpass match-ups for one site from maiac.load_sites() rows."""
    obs = read_aeronet(site)
    s = sat_sites[(sat_sites.site == site) & (sat_sites.n >= C.MATCH_MIN_PIXELS)].copy()
    if obs.empty or s.empty:
        return pd.DataFrame()
    w = pd.Timedelta(minutes=C.MATCH_WINDOW_MIN)
    t = obs.time.values
    rows = []
    for r in s.itertuples():
        lo, hi = np.searchsorted(t, np.datetime64(r.time - w)), np.searchsorted(t, np.datetime64(r.time + w), "right")
        if hi - lo >= 2:
            v = obs.aod550.values[lo:hi]
            rows.append(dict(site=site, time=r.time, sat=r.sat, sat_aod=r.aod_mean, sat_n=r.n,
                             sat_std=r.aod_std, aeronet_aod=float(v.mean()), aeronet_n=int(hi - lo)))
    return pd.DataFrame(rows)


SEASONS = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
           6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
BINS = [0, 0.2, 0.5, 1.0, np.inf]
BIN_LABELS = ["<0.2", "0.2-0.5", "0.5-1.0", ">1.0"]


def breakdown(m):
    out = {"all": stats(m.sat_aod, m.aeronet_aod)}
    out["by_satellite"] = {k: stats(g.sat_aod, g.aeronet_aod) for k, g in m.groupby("sat")}
    out["by_season"] = {k: stats(g.sat_aod, g.aeronet_aod) for k, g in m.groupby(m.time.dt.month.map(SEASONS))}
    b = pd.cut(m.aeronet_aod, BINS, labels=BIN_LABELS)
    out["by_aeronet_aod"] = {str(k): stats(g.sat_aod, g.aeronet_aod) for k, g in m.groupby(b, observed=True)}
    out["by_year"] = {int(k): stats(g.sat_aod, g.aeronet_aod) for k, g in m.groupby(m.time.dt.year)}
    return out


def availability(sat_sites, site):
    """Share of station days with at least one valid satellite match, by station AOD."""
    obs = read_aeronet(site)
    if obs.empty:
        return {}
    day = obs.groupby(obs.time.dt.floor("D")).aod550.mean()
    s = sat_sites[sat_sites.site == site]
    got = s[s.n >= C.MATCH_MIN_PIXELS].groupby(pd.to_datetime(s.time).dt.floor("D")).size()
    has = day.index.isin(got.index)
    b = pd.cut(day.values, BINS, labels=BIN_LABELS)
    return {str(k): dict(station_days=int((b == k).sum()), with_retrieval=float(has[b == k].mean()) if (b == k).any() else None)
            for k in BIN_LABELS}


def monthly_at_site(sat_monthly_site, site):
    """Satellite monthly mean at the station vs the station monthly mean of daily means."""
    obs = read_aeronet(site)
    if obs.empty:
        return pd.DataFrame()
    day = obs.groupby(obs.time.dt.floor("D")).aod550.mean()
    nd = day.groupby(day.index.to_period("M")).size()
    mon = day.groupby(day.index.to_period("M")).mean()[nd >= C.MIN_DAYS_PER_MONTH]
    j = pd.DataFrame({"aeronet_aod": mon}).join(sat_monthly_site.rename("sat_aod"), how="inner").dropna()
    j.index.name = "month"
    return j.reset_index().assign(site=site)


def run(sat_sites, sat_monthly_by_site, label="maiac"):
    """Write match-ups and a summary JSON to data/out/validation/."""
    od = C.OUT / "validation"
    od.mkdir(parents=True, exist_ok=True)
    summary, allm, allmon = {}, [], []
    for site in C.AERONET_SITES:
        m = matchups(sat_sites, site)
        if m.empty:
            continue
        mon = monthly_at_site(sat_monthly_by_site[site], site) if site in sat_monthly_by_site else pd.DataFrame()
        summary[site] = dict(
            period=[str(m.time.min().date()), str(m.time.max().date())],
            overpass=breakdown(m),
            monthly=stats(mon.sat_aod, mon.aeronet_aod) if len(mon) else {},
            availability=availability(sat_sites, site),
        )
        allm.append(m)
        allmon.append(mon)
    pd.concat(allm).to_csv(od / f"{label}_aeronet_overpass_matchups.csv", index=False, float_format="%.4f")
    pd.concat(allmon).astype({"month": str}).to_csv(od / f"{label}_aeronet_monthly.csv", index=False, float_format="%.4f")
    (od / f"{label}_validation_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def monthly_report(sat_monthly_by_site, slope, intercept, label):
    """Validation of a corrected monthly product: pairs for the scatter plot,
    scores overall, by season and by AOD level, and the worst months."""
    from .calibrate import FIT_SITE, apply

    pairs = []
    for site in C.AERONET_SITES:
        if site not in sat_monthly_by_site:
            continue
        j = monthly_at_site(sat_monthly_by_site[site], site)
        if len(j) < 3:
            continue
        j["product_aod"] = apply(j.sat_aod, slope, intercept).round(4)
        j["used_in_fit"] = site == FIT_SITE
        pairs.append(j.rename(columns={"sat_aod": "raw_aod"}))
    p = pd.concat(pairs, ignore_index=True)
    p["month"] = p.month.astype(str)
    p["season"] = pd.to_datetime(p.month).dt.month.map(SEASONS)
    p["error"] = (p.product_aod - p.aeronet_aod).round(4)
    summary = {}
    for site, g in p.groupby("site"):
        b = pd.cut(g.aeronet_aod, [0, 0.25, 0.4, np.inf], labels=["<0.25", "0.25-0.4", ">0.4"])
        summary[site] = dict(
            used_in_fit=bool(g.used_in_fit.iloc[0]),
            period=[g.month.min(), g.month.max()],
            all=stats(g.product_aod, g.aeronet_aod),
            by_season={k: stats(x.product_aod, x.aeronet_aod) for k, x in g.groupby("season")},
            by_aeronet_aod={str(k): stats(x.product_aod, x.aeronet_aod) for k, x in g.groupby(b, observed=True)},
            worst_months=g.reindex(g.error.abs().sort_values(ascending=False).index)
                         .head(5)[["month", "aeronet_aod", "product_aod", "error"]].to_dict("records"),
        )
    od = C.OUT / "validation"
    od.mkdir(parents=True, exist_ok=True)
    p[["site", "month", "season", "aeronet_aod", "raw_aod", "product_aod", "error", "used_in_fit"]].to_csv(
        od / f"{label}_monthly_validation_pairs.csv", index=False)
    (od / f"{label}_monthly_validation_summary.json").write_text(json.dumps(summary, indent=1, default=float))
    return p, summary
