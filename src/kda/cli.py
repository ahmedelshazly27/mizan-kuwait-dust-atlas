"""Command line entry point: `kda <stage>`, or `kda all` for the whole pipeline."""

import argparse
import json

STAGES = ["fetch", "maiac", "merra2", "s5p", "products", "research", "validate", "manifest"]


def run(stage):
    if stage == "fetch":
        from . import fetch_open

        fetch_open.all_open()
    elif stage == "maiac":
        from . import maiac

        maiac.run()
    elif stage == "merra2":
        from . import merra2

        merra2.run()
    elif stage == "s5p":
        # Cross-check only. Depends on NASA's Harmony and CMR services; a failure
        # here is reported but does not stop the pipeline.
        from . import s5p

        try:
            s5p.run()
        except Exception as e:
            print(f"S5P skipped: {e!r}"[:300])
    elif stage == "products":
        from . import products

        products.export()
    elif stage == "research":
        from . import maiac, products

        products.export_maiac_research(maiac.load_daily())
    elif stage == "validate":
        from . import config as C
        from . import maiac, merra2, sitemonthly, validate

        cal = json.loads((C.OUT / "validation" / "merra2_calibration.json").read_text())["correction"]
        validate.monthly_report(merra2.at_sites(), cal["slope"], cal["intercept"], "merra2")
        sites = maiac.load_sites()
        validate.run(sites, sitemonthly.from_sites(sites), label="maiac")
    elif stage == "manifest":
        from . import products

        products.manifest()


def main(argv=None):
    p = argparse.ArgumentParser(prog="kda")
    p.add_argument("stage", choices=STAGES + ["all"])
    a = p.parse_args(argv)
    for s in STAGES if a.stage == "all" else [a.stage]:
        print(f"== {s}", flush=True)
        run(s)


if __name__ == "__main__":
    main()
