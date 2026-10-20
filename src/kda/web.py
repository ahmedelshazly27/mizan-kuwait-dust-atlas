"""Small files for the website: one JSON with every number the page shows, and
three light GeoJSON layers. Nothing here is new data; it is a compact view of
data/out/, so the page never computes a value the downloads do not contain."""

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from . import config as C
from . import grid, products

SIMPLIFY_DEG = 0.002  # about 200 m: invisible at the map's zoom levels
NEIGHBOURS = ["IRQ", "SAU", "IRN"]


def _r(a, nd=3):
    return [None if not np.isfinite(x) else round(float(x), nd) for x in np.asarray(a, float)]


def build(version="1.0.0", doi=None):
    out = C.WEB
    out.mkdir(parents=True, exist_ok=True)
    r = products.export()
    corr, months, gov, cells = r["corr"], r["months"], r["gov"], r["cells"]
    gm = r["gov_monthly"]
    cal = json.loads((C.OUT / "validation" / "merra2_calibration.json").read_text())
    summ = json.loads((C.OUT / "validation" / "merra2_monthly_validation_summary.json").read_text())
    pairs = pd.read_csv(C.OUT / "validation" / "merra2_monthly_validation_pairs.csv")
    ghi = pd.read_csv(C.OUT / "kuwait_governorates_ghi_climatology_2015_2025.csv")

    def clim_of(series):
        s = pd.Series(series, index=pd.PeriodIndex(months, freq="M"))
        s = s[(s.index.year >= C.CLIM_YEARS[0]) & (s.index.year <= C.CLIM_YEARS[1])]
        return _r(s.groupby(s.index.month).mean().reindex(range(1, 13)).values)

    cell_rows = []
    for c in cells.itertuples():
        v = corr.sel(lat=c.cell_lat, lon=c.cell_lon).values
        cell_rows.append(dict(id=c.cell_id, lat=c.cell_lat, lon=c.cell_lon, area_km2=c.kuwait_area_km2,
                              aod=_r(v), clim=clim_of(v)))

    gov_rows = []
    for g in gov.itertuples():
        v = gm[gm.governorate == g.name].sort_values("month").aod550.values
        gov_rows.append(dict(id=g.iso_3166_2, name=g.name, name_ar=g.name_ar, aod=_r(v), clim=clim_of(v),
                             ghi=_r(ghi[ghi.governorate == g.name].sort_values("month").ghi_kwh_m2_day.values, 2)))

    # Kuwait as a whole: area-weighted over every land cell of the fine grid.
    gr = products.governorate_raster()
    lon, lat = grid.target_axes()
    import xarray as xr

    fine = corr.sel(lat=xr.DataArray(lat, dims="y"), lon=xr.DataArray(lon, dims="x"), method="nearest")
    kw = fine.where(xr.DataArray(gr > 0, dims=("y", "x"))).mean(["y", "x"]).values

    held = cal["Kuwait_University_corrected"]
    payload = dict(
        version=version, doi=doi, months=months, clim_years=list(C.CLIM_YEARS),
        kuwait=dict(aod=_r(kw), clim=clim_of(kw)),
        cells=cell_rows, governorates=gov_rows,
        index=dict(aod_max=products.INDEX_AOD_MAX,
                   classes=[dict(max_aod=(c[0] if np.isfinite(c[0]) else None), name=c[1]) for c in products.CLASSES]),
        correction=dict(slope=round(cal["correction"]["slope"], 3), intercept=round(cal["correction"]["intercept"], 3),
                        n_months=cal["correction"]["n_months"]),
        uncertainty=dict(rmse_held_out=round(held["rmse"], 3)),
        validation=dict(
            pairs=[dict(site=p.site, month=p.month, station=round(p.aeronet_aod, 3), product=round(p.product_aod, 3),
                        used_in_fit=bool(p.used_in_fit)) for p in pairs.itertuples()],
            sites={s: dict(used_in_fit=x["used_in_fit"], period=x["period"],
                           **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in x["all"].items()
                              if k in ("n", "r", "bias", "rmse", "within_ee")},
                           by_season={k: dict(n=y["n"], r=round(y["r"], 2), bias=round(y["bias"], 3), rmse=round(y["rmse"], 3))
                                      for k, y in x["by_season"].items()},
                           worst=[dict(month=w["month"], station=round(w["aeronet_aod"], 2), product=round(w["product_aod"], 2))
                                  for w in x["worst_months"][:3]])
                   for s, x in summ.items()},
            reverse=dict(rmse=round(cal["reverse"]["test"]["rmse"], 3), bias=round(cal["reverse"]["test"]["bias"], 3)),
        ),
        stations=[dict(id=s, lon=C.AERONET_SITES[s][0], lat=C.AERONET_SITES[s][1]) for s in summ],
    )
    (out / "atlas.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))

    # GeoJSON layers
    cg = cells[["cell_id", "geometry"]].rename(columns={"cell_id": "id"}).copy()
    cg["geometry"] = cg.geometry.simplify(SIMPLIFY_DEG)
    cg.to_file(out / "cells.geojson", driver="GeoJSON", COORDINATE_PRECISION=4)
    gg = gov[["iso_3166_2", "name", "name_ar", "geometry"]].rename(columns={"iso_3166_2": "id"}).copy()
    gg["geometry"] = gg.geometry.simplify(SIMPLIFY_DEG)
    gg.to_file(out / "governorates.geojson", driver="GeoJSON", COORDINATE_PRECISION=4)
    a1 = gpd.read_file("zip://" + str(C.RAW / "boundaries" / "ne_10m_admin_1_states_provinces.zip"))
    nb = a1[a1.adm0_a3.isin(NEIGHBOURS)].dissolve("adm0_a3").reset_index()[["adm0_a3", "geometry"]]
    nb = nb.clip((C.LON_MIN - 2, C.LAT_MIN - 2, C.LON_MAX + 2, C.LAT_MAX + 2))
    nb["geometry"] = nb.geometry.simplify(0.01)
    nb.to_file(out / "context.geojson", driver="GeoJSON", COORDINATE_PRECISION=3)
    return {p.name: p.stat().st_size for p in out.iterdir()}
