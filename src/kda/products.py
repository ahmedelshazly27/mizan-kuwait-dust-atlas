"""The published products: monthly AOD, climatology, the soiling-exposure index,
and the files people download.

Primary product: MERRA-2 total AOD at 550 nm, corrected against AERONET at
Shagaya (see calibrate.py), on MERRA-2's own 0.5 x 0.625 degree cells. The
cells are kept at that size on purpose: the data cannot resolve differences
inside Kuwait finer than that, and the files should not pretend otherwise.

Research layer: MAIAC 1 km AOD with the same kind of correction, published
separately and flagged near coasts and on islands, where it is unreliable.
"""

import hashlib
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt
from shapely.geometry import box

from . import calibrate
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

# MERRA-2 grid spacing (degrees).
M2_DLAT, M2_DLON = 0.5, 0.625
COAST_FLAG_KM = 5


def soiling_index(aod):
    return 100 * np.clip(aod / INDEX_AOD_MAX, 0, 1)


def soiling_class(aod):
    bounds = [c[0] for c in CLASSES]
    k = np.digitize(aod, bounds[:-1]).astype(float)
    return np.where(np.isfinite(aod), k + 1, np.nan)  # 1..4


def _class_names(aod):
    k = soiling_class(np.asarray(aod, float))
    names = np.array([""] + [c[1] for c in CLASSES], dtype=object)
    return names[np.nan_to_num(k, nan=0).astype(int)]


# ---------------------------------------------------------------- boundaries


def governorates():
    g = gpd.read_file("zip://" + str(C.RAW / "boundaries" / "ne_10m_admin_1_states_provinces.zip"))
    g = g[g.adm0_a3 == "KWT"][["name", "name_ar", "iso_3166_2", "geometry"]].copy()
    g["name_ar"] = g.name_ar.str.replace("محافظة ", "", regex=False).str.replace(" في الكويت", "", regex=False)
    return g.sort_values("iso_3166_2").reset_index(drop=True).to_crs(4326)


def transform():
    return from_origin(C.LON_MIN, C.LAT_MAX, C.GRID_RES, C.GRID_RES)


def governorate_raster():
    """0 outside Kuwait, else 1-based index into governorates(), on the 0.01 degree grid."""
    g = governorates()
    return rasterize(((geom, i + 1) for i, geom in enumerate(g.geometry)), out_shape=grid.shape(),
                     transform=transform(), fill=0, dtype="uint8")


# ------------------------------------------------------------------ helpers


def climatology(m):
    y0, y1 = C.CLIM_YEARS
    mm = m.sel(time=slice(f"{y0}-01-01", f"{y1}-12-31"))
    return mm.groupby("time.month").mean().rename("aod550"), mm.notnull().groupby("time.month").sum().astype("int16").rename("n_years")


def _cog(da, path, band_names, source, xdim="lon", ydim="lat"):
    da = da.transpose(..., ydim, xdim).sortby(ydim, ascending=False).rename({xdim: "x", ydim: "y"}).astype("float32")
    da.attrs = {"long_name": tuple(band_names)}  # becomes the band descriptions
    da = da.rio.write_crs(4326).rio.write_nodata(np.nan)
    da.rio.to_raster(path, driver="COG", compress="DEFLATE", predictor=3,
                     tags=dict(source=source, producer="Mizan Energy Engineering, https://mizan-energy.com", license="CC BY 4.0"))


def _month_labels(da):
    return [pd.Timestamp(t).strftime("%Y-%m") for t in da.time.values]


MONTH_NAMES = [pd.Timestamp(2000, k, 1).strftime("%B") for k in range(1, 13)]


# ---------------------------------------------------------- primary: MERRA-2


def merra2_corrected():
    """Corrected monthly MERRA-2 AOD over the box, and the correction used."""
    from . import merra2

    ds = xr.open_dataset(merra2.OUT)
    cal = calibrate.report(merra2.at_sites(ds), "merra2")["correction"]
    raw = ds.TOTEXTTAU
    raw = raw.assign_coords(time=pd.to_datetime(raw.time.values).to_period("M").to_timestamp())
    corr = xr.apply_ufunc(calibrate.apply, raw, cal["slope"], cal["intercept"]).rename("aod550")
    dust_share = (ds.DUEXTTAU / ds.TOTEXTTAU).assign_coords(time=corr.time).rename("dust_share")
    return corr, dust_share, cal


def merra2_cells(lat, lon, land_union):
    """One polygon per MERRA-2 cell that touches Kuwait, clipped to Kuwait for display."""
    rows = []
    for la in lat:
        for lo in lon:
            cell = box(lo - M2_DLON / 2, la - M2_DLAT / 2, lo + M2_DLON / 2, la + M2_DLAT / 2)
            inter = cell.intersection(land_union)
            if not inter.is_empty:
                rows.append(dict(cell_id=f"{la:+.2f}_{lo:+.3f}", cell_lat=float(la), cell_lon=float(lo),
                                 kuwait_area_km2=round(gpd.GeoSeries([inter], crs=4326).to_crs(32638).area.iloc[0] / 1e6, 1),
                                 geometry=inter, cell_geometry=cell))
    return gpd.GeoDataFrame(rows, crs=4326)


def export():
    out = C.OUT
    out.mkdir(parents=True, exist_ok=True)
    gov = governorates()
    land_union = gov.union_all()
    corr, dust_share, cal = merra2_corrected()
    months = _month_labels(corr)
    first, last = months[0], months[-1]
    clim, nyears = climatology(corr)
    src = "MERRA-2 M2TMNXAER TOTEXTTAU (AOD 550 nm), linearly corrected against AERONET Level 2.0 at Shagaya Park"

    # GeoTIFF on the native MERRA-2 grid
    _cog(clim, out / "kuwait_aod550_climatology_2015_2025.tif", MONTH_NAMES, src)
    _cog(xr.apply_ufunc(soiling_index, clim), out / "kuwait_soiling_index_climatology_2015_2025.tif", MONTH_NAMES, src)
    _cog(corr, out / f"kuwait_aod550_monthly_{first}_{last}.tif", months, src)

    # Cells touching Kuwait: tables and GeoJSON
    cells = merra2_cells(corr.lat.values, corr.lon.values, land_union)
    rows = []
    for c in cells.itertuples():
        v = corr.sel(lat=c.cell_lat, lon=c.cell_lon).values
        d = dust_share.sel(lat=c.cell_lat, lon=c.cell_lon).values
        rows.append(pd.DataFrame(dict(cell_id=c.cell_id, cell_lat=c.cell_lat, cell_lon=c.cell_lon, month=months,
                                      aod550=v.round(4), dust_share=d.round(3))))
    cm = pd.concat(rows, ignore_index=True)
    cm["soiling_index"] = soiling_index(cm.aod550).round(1)
    cm["soiling_class"] = _class_names(cm.aod550.values)
    cm.to_csv(out / f"kuwait_cells_monthly_{first}_{last}.csv", index=False)
    cm.to_parquet(out / f"kuwait_cells_monthly_{first}_{last}.parquet", index=False)

    cg = cells.drop(columns="cell_geometry").copy()
    for k in range(12):
        cg[f"aod550_{k + 1:02d}"] = [round(float(clim.isel(month=k).sel(lat=c.cell_lat, lon=c.cell_lon)), 4) for c in cells.itertuples()]
    cg["aod550_annual"] = cg[[f"aod550_{k:02d}" for k in range(1, 13)]].mean(1).round(4)
    cg.to_file(out / "kuwait_cells_climatology_2015_2025.geojson", driver="GeoJSON")

    # Governorates: area-weighted mean of the cells they overlap (via the 0.01 degree grid)
    gr = governorate_raster()
    lon, lat = grid.target_axes()
    fine = corr.sel(lat=xr.DataArray(lat, dims="y"), lon=xr.DataArray(lon, dims="x"), method="nearest")
    gm = []
    for i, row in gov.iterrows():
        mask = xr.DataArray(gr == i + 1, dims=("y", "x"))
        s = fine.where(mask).mean(["y", "x"])
        gm.append(pd.DataFrame(dict(governorate=row["name"], governorate_ar=row["name_ar"], iso_3166_2=row["iso_3166_2"],
                                    month=months, aod550=s.values.round(4))))
    gm = pd.concat(gm, ignore_index=True)
    gm["soiling_index"] = soiling_index(gm.aod550).round(1)
    gm["soiling_class"] = _class_names(gm.aod550.values)
    gm.to_csv(out / f"kuwait_governorates_monthly_{first}_{last}.csv", index=False)
    gm.to_parquet(out / f"kuwait_governorates_monthly_{first}_{last}.parquet", index=False)

    gm_clim = (gm.assign(t=pd.to_datetime(gm.month)).query(f"t.dt.year >= {C.CLIM_YEARS[0]} and t.dt.year <= {C.CLIM_YEARS[1]}")
               .groupby(["governorate", gm.month.str[5:7].astype(int).rename("m")]).aod550.mean().unstack())
    gj = gov.copy()
    for k in range(1, 13):
        gj[f"aod550_{k:02d}"] = gj.name.map(gm_clim[k]).round(4)
    gj["aod550_annual"] = gj[[f"aod550_{k:02d}" for k in range(1, 13)]].mean(1).round(4)
    gj.to_file(out / "kuwait_governorates_climatology_2015_2025.geojson", driver="GeoJSON")

    power_ghi(gov).to_csv(out / "kuwait_governorates_ghi_climatology_2015_2025.csv", index=False)

    meta = dict(
        source=src, correction=cal, first_month=first, last_month=last, clim_years=list(C.CLIM_YEARS),
        grid=dict(type="MERRA-2 native", dlat=M2_DLAT, dlon=M2_DLON, cells_touching_kuwait=len(cells)),
        index=dict(formula=f"100 * clip(AOD550 / {INDEX_AOD_MAX}, 0, 1)",
                   classes=[dict(max_aod=None if not np.isfinite(c[0]) else c[0], name=c[1], meaning=c[2]) for c in CLASSES]),
    )
    (out / "metadata.json").write_text(json.dumps(meta, indent=1))
    return dict(corr=corr, clim=clim, cells=cells, gov=gov, gov_monthly=gm, months=months)


def power_ghi(gov):
    """NASA POWER all-sky GHI (kWh/m2/day), monthly climatology per governorate.

    Context only: POWER's grid is about as coarse as MERRA-2's, so each
    governorate takes the POWER point nearest its centroid.
    """
    p = next((C.RAW / "power").glob("power_ghi_monthly_*.json"))
    feats = json.loads(p.read_text())["features"]
    rows = []
    for f in feats:
        lon, lat = f["geometry"]["coordinates"][:2]
        for k, v in f["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"].items():
            if k[4:] != "13" and v != -999 and C.CLIM_YEARS[0] <= int(k[:4]) <= C.CLIM_YEARS[1]:  # "13" = annual
                rows.append(dict(lon=lon, lat=lat, month=int(k[4:]), ghi=v))
    pts = pd.DataFrame(rows).groupby(["lon", "lat", "month"]).ghi.mean().reset_index()
    xy = pts[["lon", "lat"]].drop_duplicates().to_numpy()
    out = []
    for g in gov.itertuples():
        c = g.geometry.representative_point()
        lon, lat = xy[np.argmin((xy[:, 0] - c.x) ** 2 + (xy[:, 1] - c.y) ** 2)]
        s = pts[(pts.lon == lon) & (pts.lat == lat)]
        out.append(pd.DataFrame(dict(governorate=g.name, power_lon=lon, power_lat=lat, month=s.month,
                                     ghi_kwh_m2_day=s.ghi.round(2))))
    return pd.concat(out, ignore_index=True)


# ------------------------------------------------- research layer: MAIAC 1 km


def coastal_flag(gr):
    """True for land cells within COAST_FLAG_KM of the coast or border, and on Bubiyan/Warbah."""
    land = gr > 0
    dist_km = distance_transform_edt(land) * C.GRID_RES * 111
    lon, lat = grid.target_axes()
    LON, LAT = np.meshgrid(lon, lat)
    islands = (LON > 48.05) & (LAT > 29.55) & (LAT < 29.95)
    return land & ((dist_km <= COAST_FLAG_KM) | islands)


def export_maiac_research(daily):
    from . import maiac, sitemonthly

    out = C.OUT / "research_maiac_1km"
    out.mkdir(parents=True, exist_ok=True)
    cal = calibrate.report(sitemonthly.from_sites(maiac.load_sites()), "maiac")["correction"]
    gr = governorate_raster()
    land = gr > 0
    flag = coastal_flag(gr)

    last = pd.Timestamp(daily.time.values[-1]).normalize()
    if last != last + pd.offsets.MonthEnd(0):
        daily = daily.sel(time=slice(None, last - pd.offsets.MonthEnd(1)))
    n = daily.notnull().resample(time="MS").sum()
    m = daily.resample(time="MS").mean().where(n >= C.MIN_DAYS_PER_MONTH)
    m = xr.apply_ufunc(calibrate.apply, m, cal["slope"], cal["intercept"]).where(land).rename("aod550")
    months = _month_labels(m)
    src = "MODIS MAIAC MCD19A2 C6.1 AOD 550 nm, best-quality retrievals, linearly corrected against AERONET at Shagaya Park. RESEARCH LAYER"
    _cog(m, out / f"research_maiac_aod550_monthly_{months[0]}_{months[-1]}.tif", months, src)

    lon, lat = grid.target_axes()
    keep = land.ravel()
    gname = np.array([""] + list(governorates().name))
    base = pd.DataFrame(dict(lon=np.tile(lon, lat.size), lat=np.repeat(lat, lon.size), governorate=gname[gr.ravel()],
                             coastal_or_island=flag.ravel()))[keep]
    v = m.values.reshape(m.shape[0], -1)[:, keep]
    nd = n.values.reshape(n.shape[0], -1)[:, keep]
    df = pd.concat([base.assign(month=t) for t in months], ignore_index=True)
    df["aod550"] = v.ravel().round(4)
    df["n_days"] = nd.ravel().astype("int16")
    df.to_parquet(out / f"research_maiac_aod550_monthly_{months[0]}_{months[-1]}.parquet", index=False)
    (out / "README.txt").write_text(
        "RESEARCH LAYER, NOT THE ATLAS PRODUCT.\n\n"
        "MAIAC 1 km AOD (MCD19A2 C6.1), monthly means of best-quality retrievals, linearly corrected\n"
        f"against AERONET at Shagaya Park: AOD = max(0, {cal['slope']:.3f} * MAIAC + {cal['intercept']:.3f}).\n\n"
        "Known problems, see the main README: raw MAIAC reads about half the ground-truth AOD in dusty\n"
        "conditions; the shortfall varies by season and by site; heavy dust is often missed near the\n"
        "coast; and values near the coast and on Bubiyan/Warbah (coastal_or_island = true) are inflated\n"
        "by the tidal flats. Differences between inland cells are mostly within the error.\n"
    )
    return m


def manifest():
    """SHA-256 of every published file and every raw input, for verification."""
    lines = []
    for base in (C.OUT, C.RAW):
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix != ".part" and p.name not in ("maiac_index.json", "MANIFEST.sha256"):
                lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(C.DATA)}")
    (C.OUT / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")
