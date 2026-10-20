"""Fetch the sources that need no login: AERONET, NASA POWER, boundaries.

Each fetch is idempotent: an existing file is kept unless force=True.
"""

import json
from datetime import date

import requests

from . import config as C

UA = {"User-Agent": "kuwait-dust-atlas (https://github.com/ahmedelshazly27/mizan-kuwait-dust-atlas)"}


def _get(url, dest, force=False, timeout=600):
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.rename(dest)
    return dest


def aeronet(force=False):
    """AERONET Version 3 Level 2.0 direct-sun AOD, every observation, all Kuwait sites.

    Public domain. AERONET asks that the site PI be informed of the use and
    acknowledged; the PI is named in each file header.
    """
    end = date.today()
    out = []
    for site in C.AERONET_SITES:
        url = (
            "https://aeronet.gsfc.nasa.gov/cgi-bin/print_web_data_v3"
            f"?site={site}&year=2000&month=1&day=1"
            f"&year2={end.year}&month2={end.month}&day2={end.day}"
            "&AOD20=1&AVG=10&if_no_html=1"
        )
        out.append(_get(url, C.RAW / "aeronet" / f"{site}_L20_all.csv", force))
    return out


def boundaries(force=False):
    """Kuwait governorates (ADM1).

    Natural Earth admin-1, public domain, so it can be redistributed inside a
    CC BY dataset without conditions. geoBoundaries' Kuwait ADM1 is OSM-derived
    and ODbL, which would impose share-alike on the dataset, so it is not used.
    """
    url = (
        "https://naciscdn.org/naturalearth/10m/cultural/"
        "ne_10m_admin_1_states_provinces.zip"
    )
    return _get(url, C.RAW / "boundaries" / "ne_10m_admin_1_states_provinces.zip", force)


def power(force=False):
    """NASA POWER monthly all-sky GHI on its native 0.5 x 0.625 degree grid.

    Context only (it is MERRA-2/CERES based and coarse). Open, no restrictions;
    NASA asks for acknowledgement.
    """
    last = date.today().year - 1
    url = (
        "https://power.larc.nasa.gov/api/temporal/monthly/regional"
        "?parameters=ALLSKY_SFC_SW_DWN&community=RE"
        f"&longitude-min={C.LON_MIN}&longitude-max={C.LON_MAX}"
        # The regional endpoint needs a span of at least 2 degrees in latitude.
        "&latitude-min=28.0&latitude-max=30.5"
        f"&start={C.START[:4]}&end={last}&format=JSON"
    )
    return _get(url, C.RAW / "power" / f"power_ghi_monthly_{C.START[:4]}_{last}.json", force)


def all_open(force=False):
    return {"aeronet": aeronet(force), "boundaries": boundaries(force), "power": power(force)}


if __name__ == "__main__":
    print(json.dumps({k: [str(p) for p in (v if isinstance(v, list) else [v])] for k, v in all_open().items()}, indent=1))
