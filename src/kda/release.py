"""Archive a release on Zenodo.

    uv run python -m kda.release --sandbox --publish   # test run on sandbox.zenodo.org
    uv run python -m kda.release                       # real Zenodo: DRAFT only, DOI reserved

A draft on zenodo.org is private and can be deleted; publishing it is
permanent, so the script never publishes to the real Zenodo unless asked with
--publish. Tokens: ZENODO_SANDBOX_TOKEN / ZENODO_TOKEN (scopes deposit:write,
deposit:actions).

Uploaded: every published file in data/out/ (the research layer and the
validation tables as zip archives, since Zenodo records are flat), and a
snapshot of the code at the current git commit.
"""

import argparse
import json
import os
import subprocess
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import requests

from . import config as C
from . import http

VERSION = "1.0.0"
TITLE = "Kuwait Dust and Soiling Atlas: monthly aerosol optical depth and relative PV soiling exposure, 2015 to present"
REPO = "https://github.com/ahmedelshazly27/mizan-kuwait-dust-atlas"
PAGE = "https://mizan-energy.com/research/kuwait-dust-atlas/"


def description():
    cal = json.loads((C.OUT / "validation" / "merra2_calibration.json").read_text())
    meta = json.loads((C.OUT / "metadata.json").read_text())
    k = cal["Kuwait_University_corrected"]
    sh = cal["Shagaya_Park_corrected"]
    return f"""
<p>Monthly mean aerosol optical depth (AOD) at 550 nm over Kuwait, {meta['first_month']} to {meta['last_month']},
with a {meta['clim_years'][0]}–{meta['clim_years'][1]} climatology, a simple relative soiling-exposure index, and a
validation against AERONET Level 2.0 ground stations. Built and maintained by Mizan Energy Engineering.</p>
<p><strong>Source and method.</strong> NASA MERRA-2 total AOD (M2TMNXAER), on its native 0.5° × 0.625° grid,
linearly corrected against the AERONET station at Shagaya Park:
AOD = max(0, {cal['correction']['slope']:.3f} × MERRA-2 − {abs(cal['correction']['intercept']):.3f}).
MODIS MAIAC 1 km AOD was evaluated as the source and rejected (it reads about half the ground-truth AOD in dusty
conditions over Kuwait, with season- and site-dependent error and coastal artefacts); it is included as a
clearly labelled research layer. Index = 100 × min(AOD / 0.8, 1), with four fixed classes.</p>
<p><strong>Validation</strong> (monthly means): Kuwait University, held out of the fit: n={k['n']}, r={k['r']:.2f},
bias {k['bias']:+.3f}, RMSE {k['rmse']:.3f}. Shagaya Park, used in the fit: n={sh['n']}, r={sh['r']:.2f},
RMSE {sh['rmse']:.3f}. The product flattens extremes (clean months slightly high, dusty months slightly low).</p>
<p><strong>Limitations.</strong> AOD measures dust in the whole air column, not deposition; the index is not a
soiling rate and has not been validated against soiling measurements. No Kuwaiti ground station has
quality-assured data after May 2021, so later months are unvalidated. Cells are about 50 × 60 km; differences
between governorates are smaller than the error.</p>
<p>Full method, sources, licences and code: <a href="{REPO}">{REPO}</a>. Interactive atlas: <a href="{PAGE}">{PAGE}</a>.</p>
<p>Data CC BY 4.0; code MIT. AERONET data: we thank the PIs and staff of the Shagaya Park and Kuwait University sites.
Contains modified Copernicus Sentinel data.</p>
""".strip()


def metadata():
    # The DOI is not set here: Zenodo applies the one reserved at creation.
    m = {
        "title": TITLE,
        "upload_type": "dataset",
        "description": description(),
        "creators": [{"name": "Mizan Energy Engineering"}],
        "access_right": "open",
        "license": "cc-by-4.0",
        "version": VERSION,
        "publication_date": date.today().isoformat(),
        "keywords": ["aerosol optical depth", "dust", "photovoltaic soiling", "Kuwait", "MERRA-2", "MAIAC", "AERONET", "solar energy"],
        "related_identifiers": [
            {"identifier": REPO, "relation": "isSupplementedBy", "resource_type": "software"},
            {"identifier": PAGE, "relation": "isDocumentedBy"},
            {"identifier": "10.5067/FH9A0MLJPC7N", "relation": "isDerivedFrom", "resource_type": "dataset"},
            {"identifier": "10.5067/MODIS/MCD19A2.061", "relation": "isDerivedFrom", "resource_type": "dataset"},
        ],
        "notes": "AERONET data assimilation in MERRA-2 stopped on 29 October 2014 (Randles et al., NASA/TM-2016-104606 Vol. 45), so the 2015-2021 validation is independent of the station records.",
    }
    return m


def files_to_upload(tmp):
    out = []
    for p in sorted(C.OUT.iterdir()):
        if p.is_file():
            out.append(p)
    for sub in ("validation", "research_maiac_1km"):
        z = Path(tmp) / f"{sub}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted((C.OUT / sub).rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(C.OUT))
        out.append(z)
    src = Path(tmp) / f"mizan-kuwait-dust-atlas-v{VERSION}-source.zip"
    subprocess.run(["git", "-C", str(C.ROOT), "archive", "--format=zip", f"--prefix=mizan-kuwait-dust-atlas-v{VERSION}/",
                    "-o", str(src), "HEAD"], check=True)
    out.append(src)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sandbox", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--deposition", help="reuse an existing draft id instead of creating one")
    a = ap.parse_args(argv)

    host = "https://sandbox.zenodo.org" if a.sandbox else "https://zenodo.org"
    token = os.environ["ZENODO_SANDBOX_TOKEN" if a.sandbox else "ZENODO_TOKEN"].strip()
    s = http.session(token=False)
    s.headers["Authorization"] = f"Bearer {token}"
    api = f"{host}/api/deposit/depositions"

    if a.deposition:
        dep = s.get(f"{api}/{a.deposition}", timeout=60).json()
    else:
        # The sandbox reserves DOIs under the production prefix and then refuses
        # them at publish, so DOIs are only reserved on the real Zenodo.
        md = {"upload_type": "dataset"} if a.sandbox else {"upload_type": "dataset", "prereserve_doi": True}
        r = s.post(api, json={"metadata": md}, timeout=60)
        r.raise_for_status()
        dep = r.json()
    doi = (dep["metadata"].get("prereserve_doi") or {}).get("doi")
    print(f"draft {dep['id']}  reserved DOI {doi}")

    bucket = dep["links"]["bucket"]
    existing = {f["filename"] for f in s.get(f"{api}/{dep['id']}/files", timeout=60).json()}
    with tempfile.TemporaryDirectory() as tmp:
        for p in files_to_upload(tmp):
            if p.name in existing:
                continue
            with open(p, "rb") as fh:
                r = s.put(f"{bucket}/{p.name}", data=fh, timeout=1800)
            r.raise_for_status()
            print(f"  uploaded {p.name} ({p.stat().st_size:,} bytes)")

    r = s.put(f"{api}/{dep['id']}", json={"metadata": metadata()}, timeout=60)
    if not r.ok:
        raise SystemExit(f"metadata rejected: {r.status_code} {r.text[:800]}")
    print("metadata set;  draft:", dep["links"]["html"])

    if a.publish:
        r = s.post(f"{api}/{dep['id']}/actions/publish", timeout=300)
        if not r.ok:
            raise SystemExit(f"publish failed: {r.status_code} {r.text[:800]}")
        print("PUBLISHED:", r.json()["links"]["html"], "DOI", r.json()["doi"])
    return dep["id"], doi


if __name__ == "__main__":
    main()
