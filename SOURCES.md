# Sources and licences

Every upstream input, what we use it for, its terms, and whether this dataset
redistributes it. Raw upstream files are never committed; `uv run kda fetch`
downloads them into `data/raw/`.

| Source | Used for | Terms | In this dataset |
|---|---|---|---|
| MODIS MAIAC MCD19A2 C6.1, 1 km daily AOD (Lyapustin & Wang, 2022, doi:10.5067/MODIS/MCD19A2.061), via NASA LAADS DAAC | The AOD itself | NASA EOSDIS data: no restrictions on use or redistribution; citation requested | Derived monthly grids only. Raw granules are linked, not copied (about 120 GB). |
| MERRA-2 M2TMNXAER, monthly aerosol diagnostics (GMAO, 2015, doi:10.5067/FH9A0MLJPC7N), via GES DISC | Evaluated against MAIAC when choosing the AOD source | NASA EOSDIS data: no restrictions; citation requested | Evaluation statistics only |
| Sentinel-5P TROPOMI UV aerosol index (L2 AER_AI), via GES DISC | Independent cross-check, mid-2018 onward | Copernicus Sentinel data, free and open; attribution required: "Contains modified Copernicus Sentinel data [year]" | Cross-check statistics only |
| AERONET Version 3 Level 2.0 direct-sun AOD (Giles et al., 2019, doi:10.5194/amt-12-169-2019) | Ground truth for validation | Public domain. AERONET asks users to inform the site PI and acknowledge the site, see below | Match-up pairs (station AOD next to satellite AOD) with acknowledgement. Raw station files are linked. |
| NASA POWER monthly all-sky GHI | Irradiance context in the area panel | Open, no restrictions; acknowledgement requested | Monthly values per governorate |
| Natural Earth 1:10m admin-1 (version current at fetch time; SHA-256 recorded in `data/out/MANIFEST.sha256`) | Governorate outlines, Kuwait land mask | Public domain | Yes |

Not used: geoBoundaries Kuwait ADM1 is derived from OpenStreetMap under ODbL,
whose share-alike terms would carry into a CC BY dataset. GADM forbids
commercial use and redistribution.

## AERONET sites and PIs

| Site | Level 2.0 record | PI |
|---|---|---|
| Shagaya_Park (primary) | 2015-08 to 2019-10 | Alaa Ismail |
| Kuwait_University | 2006-2010, 2019-02 to 2021-05 | Ismail Sabbah, Hala Khalid Al-Jassar |
| Kuwait_Airport | 2009 only | Jan-Peter Muller |
| Kuwait_Inst_Sci_Res | a few days in 2015 | Pawan Gupta |
| Kuwait_University_2 | none | |

Acknowledgement: We thank Alaa Ismail, Ismail Sabbah and Hala Khalid
Al-Jassar and their staff for establishing and maintaining the Shagaya Park
and Kuwait University AERONET sites.

## Required acknowledgements, combined

Aerosol optical depth from MODIS MAIAC (MCD19A2 C6.1), NASA LAADS DAAC.
Ground observations from AERONET (NASA GSFC). Contains modified Copernicus
Sentinel data (2018-2026). Irradiance from the NASA Langley Research Center
POWER Project. Boundaries from Natural Earth.
