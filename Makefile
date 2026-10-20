# One command regenerates everything: `make` (or `uv run kda all`).
# Needs Earthdata credentials, see README "Running it".
.PHONY: all fetch test clean
all:
	uv run kda all
fetch:
	uv run kda fetch
test:
	uv run pytest -q
clean:
	rm -rf data/interim data/out data/web
