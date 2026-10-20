"""One HTTP session factory: Earthdata token plus retries with backoff.

Every request to NASA goes through this, so a dropped connection or a 5xx is
retried rather than ending a multi-hour run.
"""

import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def session(token=True):
    s = requests.Session()
    retry = Retry(total=6, connect=6, read=6, backoff_factor=2,
                  status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
    if token:
        s.headers["Authorization"] = "Bearer " + os.environ["EARTHDATA_TOKEN"].strip()
    return s
