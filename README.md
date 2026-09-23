# Santa Cruz rental price model

Predicting studio / 1-bedroom asking rents in Santa Cruz County, with Monterey
County as a comparison market. Portfolio project.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
brew install libomp          # macOS: LightGBM needs this or it fails to load
.venv/bin/python -m ipykernel install --user --name rental-prices
```

Copy `.env.example` to `.env` and fill in the RentCast and Census keys.

## Data pipeline

Run in order. Every step is reproducible from the committed cache except
`rentcast_pull.py`, which needs an API key.

```bash
python3 scripts/rentcast_pull.py --pull --circle santacruz   # D2, needs API key
python3 scripts/rentcast_pull.py --pull --circle montereyco
.venv/bin/python scripts/build_geo.py        # D1  Census place + coastline layers
.venv/bin/python scripts/build_external.py   #     ZORI + ACS tract data
.venv/bin/python scripts/clean.py            # D3  raw -> listing events
.venv/bin/python scripts/features.py         # D4  -> features.parquet
.venv/bin/python scripts/test_geo.py         #     33 validation checks
```

No data is committed. Every file under `data/` is either downloaded or
script-generated, so the repo holds code only and the pipeline regenerates
everything. The two Census/Zillow build steps need no credentials; the
RentCast pulls need an API key and cost 23 requests against the free tier's
50/month.

Committed exceptions are `data/external/` (112 KB of public-domain Census and
Zillow research summaries) and `data/processed/clean_filter_log.csv`, so the
cleaning decisions stay reviewable without a rerun.

**RentCast data is not redistributed here.** Their licensing covers derivative
works and distribution to end users of your application, but does not clearly
permit republishing their property records as a public dataset, so the raw
cache stays local.

## Dataset

`data/processed/features.parquet` — 11,283 listing events, 2020–2026, across
Santa Cruz and Monterey counties. **3,038 are studio/1br**, the modeling slice.

One row is a *listing event*, not a property. RentCast returns one record per
property with past listings in a `history` object; `clean.py` expands those and
then collapses re-posting churn (same price within 120 days).

### Key features

| Feature | Source | Note |
|---|---|---|
| `price`, `log_price` | RentCast | asking rent, the target |
| `real_price` | ZORI-deflated | rent in 2026-01 dollars |
| `bedrooms` `bathrooms` `squareFootage` | RentCast | sqft 21% missing, see `sqft_missing` |
| `place`, `place_kind` | Census polygons | sub-market; better than mailing `city` |
| `dist_coast_mi` | TIGER coastline | |
| `dist_ucsc_mi` `dist_csumb_mi` `dist_university_mi` | hand-coded | |
| `dist_hwy17_mi` | hand-coded | Silicon Valley commute proxy |
| `dist_sc_downtown_mi` | hand-coded | absolute position in the regional market |
| `dist_town_center_mi` | hand-coded | within-town centrality only; near-zero on its own |
| `months_since_2020` | derived | time index; rents rose ~29% over the window |
| `is_turnover_season` | derived | Jul–Sep university lease turnover |
| `zori_zip` | Zillow ZORI | ZIP rent index at listing month; 70% coverage, see `zori_missing` |
| `tract_*` | ACS 2024 5-year | income, gross rent, % renter, density |

## Known limitations

- **ADU and cottage coverage.** RentCast draws on MLS and syndicated feeds,
  which under-represent the detached cottages, in-law units and garage
  conversions that make up much of the real studio/1br market here. The model
  describes *professionally listed* units. This gap is unmeasured.
- **No amenity data.** The API returns no listing description, so utilities,
  furnished, parking, laundry and pets are unavailable at any price.
- **Asking rent, not contract rent.** Long-tenured below-market tenancies never
  appear.
- **`yearBuilt` is 18% populated**, `lotSize` 8%. Effectively unusable.
- **Market-level features are strong priors.** `zori_zip` and
  `tract_median_gross_rent` are aggregates partly derived from the same rents
  being predicted. They are legitimately known at prediction time, but a model
  leaning on them is learning less about the individual property than its
  accuracy suggests. Worth an ablation.

## Modeling notes

- **Split temporally.** The data spans 2020–2026 with ~29% drift. A random
  split leaks the future.
- **Group by property.** `id` is address-derived; the same unit recurs across
  years. Keep a property's events on one side of the split.
- **Report a baseline.** Median rent by (`place` × `bedrooms`) is the number to
  beat.
- `real_price` as an alternative target checks whether the model is learning
  property characteristics or just the passage of time.

## API quota

RentCast free tier is 50 requests/month. `data/quota_log.jsonl` tracks usage;
`scripts/rentcast_pull.py --status` reports it. 24 used as of 2026-09-22.
