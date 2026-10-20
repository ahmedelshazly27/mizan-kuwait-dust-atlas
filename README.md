# Kuwait Dust and Soiling Atlas

Monthly aerosol optical depth (AOD, 550 nm) over Kuwait on a 0.01 degree grid,
2015 to present, with a simple relative soiling-exposure index and a
validation against ground stations. Built and maintained by
[Mizan](https://mizan-energy.com). Data CC BY 4.0, code MIT.

> Status: under construction. The method below is fixed. The numbers are not
> published yet.

## Running it

```bash
git clone https://github.com/ahmedelshazly27/mizan-kuwait-dust-atlas
cd mizan-kuwait-dust-atlas
cp .env.example .env    # add your NASA Earthdata login (free: urs.earthdata.nasa.gov)
make                    # = uv run kda all
```

Requires [uv](https://docs.astral.sh/uv/). All dependencies are pinned in
`pyproject.toml` and `uv.lock`. The full MAIAC download is about 120 GB, but
each day is cut to Kuwait and discarded as it arrives, so peak disk use is
small. Expect several hours.

## Method in brief

1. **AOD.** MODIS MAIAC MCD19A2 C6.1, Terra and Aqua, every overpass. Keep
   only retrievals flagged clear and not adjacent to cloud (the product's
   best-quality filter). Average each day's overpasses per pixel.
2. **Grid.** Each 0.01 degree cell averages the 1 to 3 sinusoidal 1 km pixels
   whose centres fall inside it.
3. **Monthly means.** Mean of daily values per cell per month; a cell needs
   at least 5 valid days in the month or the month is left empty.
4. **Climatology.** Mean of the monthly means per calendar month over the
   complete years 2015 to 2025.
5. **Soiling-exposure index.** A fixed rescaling of monthly AOD into four
   classes. It ranks relative dust exposure; it is not a soiling loss rate.
   See "Limitations".
6. **Validation.** Against AERONET Level 2.0 within 5 km and 30 minutes of
   each overpass, plus monthly means.

## Limitations

- **AOD is not deposition.** AOD measures the whole atmospheric column.
  Soiling depends on near-surface concentration, particle size, wind, dew,
  rain and how often panels are cleaned. None of that is in the index.
- **The index is unvalidated.** The validation tests the AOD. There are no
  public soiling measurements in Kuwait to test the index against.
- **No ground truth after May 2021.** Shagaya Park has Level 2.0 data from
  2015-08 to 2019-10, and Kuwait University from 2019-02 to 2021-05. No
  Kuwait station has quality-assured data after that, so 2021 onward is
  unvalidated.
- **Two validation points.** One inland desert site and one coastal urban
  site; nothing in the south or on the islands.
- **Satellite orbits drifted.** After orbit maintenance ended (Terra in 2020,
  Aqua in 2022), Terra's overpass drifted earlier in the morning and Aqua's
  later in the afternoon. Dust varies through the day, so this can shift
  monthly means a little, and it falls in the unvalidated period.
- **Heavy dust can be mistaken for cloud.** The validation reports how often
  MAIAC has no retrieval on days the ground station saw heavy dust.

## Licences and sources

See [SOURCES.md](SOURCES.md). Data: [CC BY 4.0](LICENSE-DATA). Code: [MIT](LICENSE).
Cite via [CITATION.cff](CITATION.cff).
