"""Command line entry point: `kda <stage>`, or `kda all` for the whole pipeline."""

import argparse

STAGES = ["fetch", "maiac", "products", "validate", "manifest"]


def run(stage):
    if stage == "fetch":
        from . import fetch_open

        fetch_open.all_open()
    elif stage == "maiac":
        from . import maiac

        maiac.run()
    elif stage == "products":
        from . import maiac, products

        products.export(maiac.load_daily())
    elif stage == "validate":
        from . import maiac, sitemonthly, validate

        sites = maiac.load_sites()
        validate.run(sites, sitemonthly.from_sites(sites))
    elif stage == "manifest":
        from . import products

        products.manifest()


def main(argv=None):
    p = argparse.ArgumentParser(prog="kda")
    p.add_argument("stage", choices=STAGES + ["all"])
    a = p.parse_args(argv)
    for s in STAGES if a.stage == "all" else [a.stage]:
        print(f"== {s}")
        run(s)


if __name__ == "__main__":
    main()
