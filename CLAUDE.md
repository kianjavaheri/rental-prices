# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A rent prediction model for **studios and one-bedrooms** in Santa Cruz and
Monterey counties, plus a static web app that runs it in the browser. It is a
portfolio project: methodology rigour and honest reporting matter more than
squeezing out accuracy.

The model prices a unit *against the prevailing market*. It does **not** forecast
the market — where the market sits on a future date comes from a fitted trend
line, not from evidence. Do not describe it as a forecasting model.

## Layout

```
scripts/           the pipeline, run in this order
  rentcast_pull.py   D2  raw listings -> data/raw/ (write-once cache)
  build_geo.py       D1  Census place + coastline layers
  build_external.py      ZORI + ACS tract data
  clean.py           D3  raw -> listing events (dedup, churn collapse, filters)
  features.py        D4  -> data/processed/features.parquet
  geo.py                 shared geographic feature derivation
  test_geo.py            33 validation checks -- run after touching geo.py
  export_web.py          model + geography -> web/public/model/
notebooks/
  01_modeling.ipynb  the analysis: baseline -> ridge -> LightGBM -> intervals
web/                 React + Vite app, runs the model client-side
```

## Commands

```bash
.venv/bin/python scripts/clean.py && .venv/bin/python scripts/features.py
.venv/bin/python scripts/test_geo.py            # must print ALL CHECKS PASSED
.venv/bin/python scripts/export_web.py          # after any model change

cd web
npm run dev                                     # localhost:5173
npm run build
npm run verify                                  # JS model == Python model
node scripts/verify_features.mjs                # JS features == Python features
```

Python is `3.14` in `.venv`. LightGBM needs `brew install libomp` on macOS.

## Rules that are easy to get wrong

**Never commit RentCast data.** `data/raw/` is gitignored deliberately. Their
licensing covers derivative works but not republishing their records. The model,
and aggregates derived from it, are fine. Addresses paired with rents are not —
`web/public/model/blocks.json` is deliberately coarsened (coordinates rounded to
3dp, street numbers stripped) for this reason. Do not "improve" it back to exact
addresses.

**The split has two leakage traps and they conflict.** Split on a date
(2026-01-01), then drop from *train* any building that also appears in test.
Group on rounded coordinates, not `id` — `latitude`/`longitude` fingerprint a
building, so units in the same complex must not straddle the split.

**Trees cannot extrapolate.** All test dates are past the training range, so the
model is trend + trees on the residual: a linear model carries the date, the
trees learn only deviation from it. Do not feed `months_since_2020` to trees as
the sole time signal and expect future dates to work.

**Never use `price_per_sqft`, `rent_vs_zip_zori` or `daysOnMarket` as features.**
The first two are computed from price; the third is downstream of it.

**The web model is deliberately smaller than the notebook model.** 18 features
(12.9% MAPE) vs 24 (12.6%). The six omitted ones are tract/ZIP market averages
needing ~2 MB of polygons to compute exactly in-browser. If you change the
feature set, re-run both verify scripts — the browser must reproduce Python
exactly, and "close enough" is not the standard here.

**After changing anything in `scripts/geo.py`,** run `test_geo.py`. Reference
points are hand-coded and validated against Census polygons; a wrong coordinate
silently corrupts a feature.

## Known data problems

- Some coordinates are wrong at the source: 116 and 200 West Cliff Drive are
  geocoded ~0.5 mi inland.
- `squareFootage` had building-footprint values (13,032 sqft on a 1BR). Capped
  by bedroom count in `clean.py`; do not remove that filter.
- `yearBuilt` is 85% missing in this slice, `lotSize` 92%. Both unusable.
- RentCast's `city` is the *mailing* city and is unreliable. Use the
  Census-polygon `place` from `geo.py`.
- No listing descriptions exist, so amenities, views and renovations are
  invisible. This is the main cause of regression to the mean at the extremes.

## Reporting results

Always quote error alongside the baseline (median by `place` x `bedrooms`,
15.2% MAPE) and break it out by sub-market — the headline 12.6% hides a 9-17%
range. Intervals are conformal, calibrated on held-out data; the coverage claim
(~80%) must be verified, not assumed.
