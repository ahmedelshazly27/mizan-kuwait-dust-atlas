"""Linear correction of a gridded AOD source against AERONET, with a held-out test.

The correction is fitted at the primary site (Shagaya Park: inland desert, the
longest record, and the setting most PV plants in Kuwait share) on monthly
means, because the published product is monthly. It is then tested on Kuwait
University, which the fit never sees. The reverse direction is reported too,
as a check that the result does not hinge on which site is held out.

Monthly means on both sides need MIN_DAYS_PER_MONTH station days.
"""

import json

import numpy as np

from . import config as C
from . import validate as V

FIT_SITE = C.PRIMARY_SITE
TEST_SITE = "Kuwait_University"


def fit(sat_monthly_by_site, fit_site=FIT_SITE):
    j = V.monthly_at_site(sat_monthly_by_site[fit_site], fit_site)
    slope, intercept = np.polyfit(j.sat_aod, j.aeronet_aod, 1)
    return float(slope), float(intercept), len(j)


def apply(x, slope, intercept):
    return np.maximum(slope * x + intercept, 0.0)


def report(sat_monthly_by_site, label):
    """Fit, held-out test, reverse test, and raw scores; written to data/out/validation/."""
    out = {"source": label, "fit_site": FIT_SITE, "test_site": TEST_SITE}
    a, b, n = fit(sat_monthly_by_site)
    out["correction"] = dict(formula="AOD_corrected = max(0, slope * AOD_raw + intercept)", slope=a, intercept=b, n_months=n)
    for site in (FIT_SITE, TEST_SITE):
        j = V.monthly_at_site(sat_monthly_by_site[site], site)
        out[f"{site}_raw"] = V.stats(j.sat_aod, j.aeronet_aod)
        out[f"{site}_corrected"] = V.stats(apply(j.sat_aod, a, b), j.aeronet_aod)
        out[f"{site}_corrected"]["in_sample"] = site == FIT_SITE
    ra, rb, rn = fit(sat_monthly_by_site, TEST_SITE)
    j = V.monthly_at_site(sat_monthly_by_site[FIT_SITE], FIT_SITE)
    out["reverse"] = dict(fit_site=TEST_SITE, slope=ra, intercept=rb, n_months=rn,
                          test=V.stats(apply(j.sat_aod, ra, rb), j.aeronet_aod))
    od = C.OUT / "validation"
    od.mkdir(parents=True, exist_ok=True)
    (od / f"{label}_calibration.json").write_text(json.dumps(out, indent=1))
    return out
