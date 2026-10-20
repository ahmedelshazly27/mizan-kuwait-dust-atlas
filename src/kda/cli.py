"""Command line entry point: `kda <stage>`, or `kda all` for the whole pipeline."""

import argparse

STAGES = ["fetch"]


def run(stage):
    if stage == "fetch":
        from . import fetch_open

        fetch_open.all_open()


def main(argv=None):
    p = argparse.ArgumentParser(prog="kda")
    p.add_argument("stage", choices=STAGES + ["all"])
    a = p.parse_args(argv)
    for s in STAGES if a.stage == "all" else [a.stage]:
        print(f"== {s}")
        run(s)


if __name__ == "__main__":
    main()
