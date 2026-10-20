# Kuwait Dust and Soiling Atlas

Monthly aerosol optical depth (AOD, 550 nm) over Kuwait, January 2015 to the
last complete month, with a 2015–2025 climatology, a simple relative
soiling-exposure index, and a validation against ground stations that
reports where it performs badly. Built and maintained by
[Mizan](https://mizan-energy.com). Data [CC BY 4.0](LICENSE-DATA), code
[MIT](LICENSE).

Interactive atlas: <https://mizan-energy.com/research/kuwait-dust-atlas>

## Read this first

- **The map is coarse on purpose.** Values come on MERRA-2 cells of about
  50 × 60 km; 12 cells cover Kuwait. Satellite data cannot currently resolve
  dust differences *inside* Kuwait reliably, and the governorates differ by
  less than the error (annual means 0.32–0.34). The useful signal is the
  **season**: monthly AOD roughly doubles from January (0.21) to April–May (0.43).
- **The index ranks dust in the air, not soiling.** Nothing here measures how
  fast panels get dirty. See [Limitations](#limitations).
- **Validated 2015–2021 only.** No Kuwaiti ground station has quality-assured
  data after May 2021.

## Running it

```bash
git clone https://github.com/ahmedelshazly27/mizan-kuwait-dust-atlas
cd mizan-kuwait-dust-atlas
export EARTHDATA_TOKEN=...   # free: urs.earthdata.nasa.gov → Generate Token
make                         # = uv run kda all
```

Requires [uv](https://docs.astral.sh/uv/). All dependencies are pinned
(`pyproject.toml`, `uv.lock`). Your Earthdata account must have the **NASA
GESDISC DATA ARCHIVE** application approved (Applications → Authorized Apps)
and, for the Sentinel-5P cross-check, the Copernicus Sentinel licence
accepted. Every stage resumes where it stopped.

| Stage | What it does | Time |
|---|---|---|
| `fetch` | AERONET, NASA POWER, Natural Earth boundaries | 1 min |
| `maiac` | MODIS MAIAC, ~4,300 days, cut to Kuwait as downloaded (~120 GB streamed, little kept) | ~1 h |
| `merra2` | MERRA-2 monthly aerosol, cut to Kuwait (~12 GB streamed) | ~15 min |
| `s5p` | Sentinel-5P aerosol index via NASA Harmony (cross-check; skipped if the service is down) | hours |
| `products` | Corrected MERRA-2 product, index, all download files | 1 min |
| `research` | MAIAC 1 km research layer | 2 min |
| `validate` | Validation tables and summaries | 1 min |
| `web` | Compact JSON and GeoJSON for the atlas page (`data/web/`) | 1 min |
| `manifest` | SHA-256 of every output and raw input | 1 min |

## Method

### 1. Which AOD source, and why

We evaluated both sources the brief named against AERONET Level 2.0 at the two
Kuwaiti stations with usable records, on monthly means (what the map shows):

| Monthly AOD vs AERONET | Shagaya Park (2015-08 to 2019-10, n=45) | Kuwait University (2019-03 to 2021-05, n=26) |
|---|---|---|
| MODIS MAIAC 1 km, raw | r 0.66, bias −0.147, RMSE 0.169 | r 0.50, bias −0.135, RMSE 0.152 |
| MERRA-2, raw | r 0.82, bias +0.139, RMSE 0.154 | r 0.75, bias +0.147, RMSE 0.158 |

**MAIAC was rejected as the primary source**, for three reasons found in the
data:

1. It reads about half the true AOD in ordinary dusty conditions (mean 0.135
   against 0.292 at Shagaya, per overpass). Its shortfall grows with dust
   (bias −0.38 when the station sees 0.5–1.0) and changes with season (the
   station sees 1.7 times MAIAC in winter, 2.7 times in spring), so a single
   correction cannot fix it. On the raw pixels, MAIAC only switched to its
   dust aerosol model on the most extreme days.
2. At the coastal station it misses heavy dust: only 17% of days with
   station AOD above 1.0 have a MAIAC retrieval, against 75% of clear days.
3. Its 1 km detail is mostly artefact. Inland, annual means vary only
   0.15–0.20 (within its error); the "hot spots" are Bubiyan and Warbah
   islands and coastal tidal flats (mean 0.51), a known surface problem, not
   dust.

**MERRA-2 was chosen.** It tracks month-to-month changes better (r 0.82 and
0.75) and its error is mostly a constant offset, which a correction can
remove. It is a reanalysis: a model that assimilates satellite AOD. AERONET
data assimilation in MERRA-2 **stopped on 29 October 2014** (Randles et al.,
2016, NASA/TM–2016-104606 Vol. 45), so the 2015–2021 validation here is
independent of the station records themselves. One indirect link remains:
the MODIS AOD that MERRA-2 assimilates was bias-corrected against the global
AERONET network.

### 2. Correction

A straight line fitted on monthly means at Shagaya Park:

```
AOD = max(0, 0.855 × MERRA-2 total AOD − 0.073)
```

Shagaya is inland desert, the setting most Kuwaiti PV plants share, and has
the longest record. The correction partly fixes MERRA-2's own bias and partly
its sampling: MERRA-2 averages all hours and all skies, AERONET measures in
clear daylight. The corrected product is therefore an estimate of the
**clear-sky daytime monthly AOD a sun photometer would record**.

### 3. Monthly series and climatology

Corrected monthly AOD per MERRA-2 cell. Climatology: mean per calendar month
over the complete years 2015–2025, so every month has 11 years behind it.
Governorate values are area-weighted means of the cells they overlap.

### 4. Soiling-exposure index

```
index = 100 × min(AOD / 0.8, 1)
```

with four classes on the same scale:

| Class | Monthly AOD | Meaning |
|---|---|---|
| Low | < 0.20 | Clearer air than usual for Kuwait |
| Moderate | 0.20–0.35 | About the usual background haze of dust for Kuwait |
| High | 0.35–0.50 | More dust in the air than usual: typical of the spring and early-summer dust season |
| Very high | ≥ 0.50 | Heavy dust in the air for much of the month |

The breakpoints are fixed numbers, not percentiles of this dataset, so a class
means the same thing in every month and every future release. Over 2015–2026
the shares are Low 12%, Moderate 51%, High 34%, Very high 4%.

## Validation

Corrected MERRA-2 against AERONET Level 2.0, monthly means (stations need at
least 5 days in a month). Full tables in `data/out/validation/`.

| | n | r | Bias | RMSE | Within ±(0.05 + 15%) |
|---|---|---|---|---|---|
| Kuwait University, **held out** (not used in the fit) | 26 | 0.75 | +0.007 | 0.055 | 88% |
| Shagaya Park, used in the fit | 45 | 0.82 | 0.000 | 0.064 | 82% |
| Shagaya, with the fit made at Kuwait University instead | 45 | 0.82 | −0.005 | 0.067 | |

### Where it performs badly

- **It flattens the extremes.** Clean months come out too high (bias +0.04
  when the station sees under 0.25) and dusty months too low (−0.06 above
  0.4). The worst month is August 2015 at Shagaya: 0.37 against a measured 0.53.
- **Summer at Shagaya is the weakest season:** r 0.55, RMSE 0.088.
- **Winter at Kuwait University barely correlates** (r 0.35, n=6), although
  errors are small because winter AOD is low.
- **Spatial pattern is unvalidated.** Two stations 90 km apart cannot test
  differences across Kuwait.

## Outputs

`data/out/` (also on Zenodo, and as direct downloads on the atlas page):

| File | Contents |
|---|---|
| `kuwait_aod550_climatology_2015_2025.tif` | 12-band Cloud Optimized GeoTIFF, native MERRA-2 grid |
| `kuwait_soiling_index_climatology_2015_2025.tif` | Same, index 0–100 |
| `kuwait_aod550_monthly_<first>_<last>.tif` | One band per month |
| `kuwait_cells_monthly_*.csv` / `.parquet` | Per cell, per month: AOD, dust share, index, class |
| `kuwait_governorates_monthly_*.csv` / `.parquet` | Per governorate, per month |
| `kuwait_cells_climatology_2015_2025.geojson` | Cells clipped to Kuwait, monthly climatology |
| `kuwait_governorates_climatology_2015_2025.geojson` | Governorates, monthly climatology |
| `validation/` | Calibration, station pairs, summaries, MAIAC match-ups |
| `research_maiac_1km/` | MAIAC 1 km monthly, corrected, with a `coastal_or_island` flag. **Research layer, not the atlas product.** |
| `metadata.json`, `MANIFEST.sha256` | Parameters used; checksums of outputs and raw inputs |

## Limitations

- **AOD is not deposition.** AOD measures the whole atmospheric column.
  Soiling depends on near-surface concentration, particle size, wind, dew,
  rain and cleaning schedules; none of that is in the index.
- **The index is unvalidated.** The validation tests the AOD. There are no
  public soiling measurements in Kuwait to test the index against.
- **No ground truth after May 2021.** Every number from mid-2021 onward rests
  on the 2015–2021 correction still holding.
- **Two stations.** One inland desert, one coastal urban; nothing in the south,
  the far west or the islands.
- **Coarse cells.** About 50 × 60 km. Cells on the coast mix land and sea.
- **Reanalysis, not observation.** Months with little satellite data lean
  more on the model.
- **One missing MAIAC day** (2020-07-05) has no file for our tiles in the
  archive; it affects only the research layer.

## Licences and sources

See [SOURCES.md](SOURCES.md). Cite via [CITATION.cff](CITATION.cff).
