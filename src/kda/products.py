"""From daily grids to the published products: monthly means, climatology,
the soiling-exposure index, and the files people download."""

import hashlib
import json
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from rasterio.features import rasterize
from rasterio.transform import from_origin

from . import config as C
from . import grid

# --------------------------------------------------------------------- index
# The soiling-exposure index. Deliberately simple: a fixed rescaling of monthly
# mean AOD at 550 nm. Fixed (not relative to this dataset) so that a value means
# the same thing in every month, every year and every future release.
#
#   index = 100 * clip(AOD / INDEX_AOD_MAX, 0, 1)
#
# and four named classes on the same AOD scale.
INDEX_AOD_MAX = 0.8
# The wording says what the AOD shows (dust in the air), never a soiling rate,
# which this index cannot measure.
CLASSES = [  # (upper AOD bound, name, plain-language meaning)
    (0.20, "Low", "Clearer air than usual for Kuwait."),
    (0.35, "Moderate", "About the usual background haze of dust for Kuwait."),
    (0.50, "High", "More dust in the air than usual: typical of the spring and early-summer dust season."),
    (np.inf, "Very high", "Heavy dust in the air for much of the month."),
]


def soiling_index(aod):
    return 100 * np.clip(aod / INDEX_AOD_MAX, 0, 1)


def soiling_class(aod):
    bounds = [c[0] for c in CLASSES]
    k = np.digitize(aod, bounds[:-1]).astype(float)
    return np.where(np.isfinite(aod), k + 1, np.nan)  # 1..4


# ---------------------------------------------------------------- boundaries


def governorates():
    g = gpd.read_file("zip://" + str(C.RAW / "boundaries" / "ne_10m_admin_1_states_provinces.zip"))
    g = g[g.adm0_a3 == "KWT"][["name", "name_ar", "iso_3166_2", "geometry"]].copy()
    g["name_ar"] = g.name_ar.str.replace("محافظة ", "", regex=False).str.replace(" في الكويت", "", regex=False)
    return g.sort_values("iso_3166_2").reset_index(drop=True).to_crs(4326)


def transform():
    return from_origin(C.LON_MIN, C.LAT_MAX, C.GRID_RES, C.GRID_RES)


def governorate_raster():
    """0 outside Kuwait, else 1-based index into governorates()."""
    g = governorates()
    return rasterize(((geom, i + 1) for i, geom in enumerate(g.geometry)), out_shape=grid.shape(),
                     transform=transform(), fill=0, dtype="uint8")


# ------------------------------------------------------------------ monthly


def monthly(daily):
    """Monthly mean of daily values and the number of valid days per cell."""
    n = daily.notnull().resample(time="MS").sum()
    m = daily.resample(time="MS").mean()
    m = m.where(n >= C.MIN_DAYS_PER_MONTH)
    return m.rename("aod550"), n.rename("n_days").astype("int16")


def complete_months(daily):
    """Drop a trailing month that is not yet complete in the daily record."""
    last = pd.Timestamp(daily.time.values[-1])
    end = last.normalize() + pd.offsets.MonthEnd(0)
    return daily if last.normalize() == end else daily.sel(time=slice(None, last.normalize() - pd.offsets.MonthEnd(1)))


def climatology(m):
    y0, y1 = C.CLIM_YEARS
    mm = m.sel(time=slice(f"{y0}-01-01", f"{y1}-12-31"))
    clim = mm.groupby("time.month").mean()
    nyears = mm.notnull().groupby("time.month").sum().astype("int16")
    return clim.rename("aod550"), nyears.rename("n_years")


# ------------------------------------------------------------------ exports


def _cog(da, path, band_names, nodata=np.nan):
    da = da.rio.write_crs(4326).rio.set_spatial_dims(x_dim="lon", y_dim="lat")
    da.attrs = {}
    da.rio.write_nodata(nodata, inplace=True)
    da.astype("float32").rio.to_raster(path, driver="COG", compress="DEFLATE", predictor=3)
    import rasterio

    with rasterio.open(path, "r+") as r:
        for i, b in enumerate(band_names, 1):
            r.set_band_description(i, b)
        r.update_tags(
            source="MODIS MAIAC MCD19A2 C6.1 AOD 550 nm, best-quality retrievals",
            producer="Mizan Energy Engineering, https://mizan-energy.com",
            license="CC BY 4.0",
        )


def export(daily):
    out = C.OUT
    out.mkdir(parents=True, exist_ok=True)
    gov = governorates()
    gr = governorate_raster()
    land = gr > 0
    lon, lat = grid.target_axes()
    daily = complete_months(daily)

    m, n = monthly(daily)
    m = m.where(land)
    clim, nyears = climatology(m)
    months = [pd.Timestamp(t).strftime("%Y-%m") for t in m.time.values]
    mnames = [pd.Timestamp(2000, k, 1).strftime("%B") for k in range(1, 13)]
    first, last = months[0], months[-1]

    # GeoTIFF (COG)
    _cog(clim, out / "kuwait_aod550_climatology_2015_2025.tif", mnames)
    _cog(xr.apply_ufunc(soiling_index, clim), out / "kuwait_soiling_index_climatology_2015_2025.tif", mnames)
    _cog(m, out / f"kuwait_aod550_monthly_{first}_{last}.tif", months)

    # Long tables
    gname = np.array([""] + list(gov.name))
    cells = pd.DataFrame({"lon": np.tile(lon, lat.size), "lat": np.repeat(lat, lon.size), "governorate": gname[gr.ravel()]})
    keep = land.ravel()

    def long(da, label, extra=None):
        v = da.values.reshape(da.shape[0], -1)[:, keep]
        df = pd.concat([cells[keep].assign(**{label: t}) for t in da[da.dims[0]].values], ignore_index=True)
        df["aod550"] = v.ravel().round(4)
        if extra is not None:
            df[extra.name] = extra.values.reshape(extra.shape[0], -1)[:, keep].ravel()
        df["soiling_index"] = soiling_index(df.aod550).round(1)
        df["soiling_class"] = _class_names(df.aod550.values)
        return df

    mon = long(m, "month", n.where(land).fillna(0).astype("int16"))
    mon["month"] = pd.to_datetime(mon.month).dt.strftime("%Y-%m")
    mon.to_parquet(out / f"kuwait_aod550_monthly_{first}_{last}.parquet", index=False)

    cl = long(clim, "calendar_month", nyears.where(land).fillna(0).astype("int16"))
    cl.to_parquet(out / "kuwait_aod550_climatology_2015_2025.parquet", index=False)
    cl.to_csv(out / "kuwait_aod550_climatology_2015_2025.csv", index=False)

    # Governorate means: monthly series and climatology
    gm = []
    for i, row in gov.iterrows():
        mask = gr == i + 1
        s = m.where(mask).mean(["lat", "lon"])
        cov = m.where(mask).notnull().sum(["lat", "lon"]) / mask.sum()
        gm.append(pd.DataFrame({"governorate": row["name"], "month": months, "aod550": s.values.round(4),
                                "cell_coverage": cov.values.round(3)}))
    gm = pd.concat(gm, ignore_index=True)
    gm["soiling_index"] = soiling_index(gm.aod550).round(1)
    gm["soiling_class"] = _class_names(gm.aod550.values)
    gm.to_csv(out / f"kuwait_governorates_monthly_{first}_{last}.csv", index=False)
    gm.to_parquet(out / f"kuwait_governorates_monthly_{first}_{last}.parquet", index=False)

    # GeoJSON: governorates with their climatology
    gj = gov.copy()
    for k in range(12):
        gj[f"aod550_{k + 1:02d}"] = [round(float(clim.isel(month=k).where(gr == i + 1).mean()), 4) for i in range(len(gov))]
    gj["aod550_annual"] = gj[[f"aod550_{k:02d}" for k in range(1, 13)]].mean(1).round(4)
    gj.to_file(out / "kuwait_governorates_climatology_2015_2025.geojson", driver="GeoJSON")

    meta = dict(first_month=first, last_month=last, clim_years=list(C.CLIM_YEARS), grid_res_deg=C.GRID_RES,
                bbox=[C.LON_MIN, C.LAT_MIN, C.LON_MAX, C.LAT_MAX], min_days_per_month=C.MIN_DAYS_PER_MONTH,
                index=dict(formula="100 * clip(AOD550 / %g, 0, 1)" % INDEX_AOD_MAX,
                           classes=[dict(max_aod=None if not np.isfinite(c[0]) else c[0], name=c[1], meaning=c[2]) for c in CLASSES]))
    (out / "metadata.json").write_text(json.dumps(meta, indent=1))
    return dict(monthly=m, n_days=n, clim=clim, gov=gov, gov_raster=gr, months=months)


def _class_names(aod):
    k = soiling_class(np.asarray(aod, float))
    names = np.array([""] + [c[1] for c in CLASSES], dtype=object)
    return names[np.nan_to_num(k, nan=0).astype(int)]


def manifest():
    """SHA-256 of every published file and every raw input, for verification."""
    lines = []
    for base in (C.OUT, C.RAW):
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix not in (".part",) and "maiac_index" not in p.name:
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                lines.append(f"{h}  {p.relative_to(C.DATA)}")
    (C.OUT / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")
