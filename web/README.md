# Rent model — web app

An interactive front end for the studio/1BR rent model. Everything runs in the
browser: the 600-tree LightGBM model, the geographic feature derivation and the
prediction intervals. No backend, no API keys.

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # -> dist/, deployable to any static host
npm run verify       # confirms the JS model matches Python
```

## How it works

`../scripts/export_web.py` writes everything the app needs into `public/model/`:

| file | what it is |
|---|---|
| `trees.json` | the 600 trees, feature order, category vocabularies |
| `meta.json` | trend line, conformal half-width `k`, medians, reference points |
| `regions.geojson` | place polygons — gives `place`, `place_kind`, `county` |
| `counties.geojson` | county outlines, for points outside every place |
| `coastline.geojson` | shoreline, unsimplified, for distance-to-ocean |
| `properties.json` | the 2,665 units: location, attributes, rent history |
| `fixture.json` | 300 listings with Python predictions, for verification |

`src/lib/lgbm.js` walks the trees, reproducing LightGBM's decision logic
including NaN routing and categorical bitset splits. `src/lib/features.js`
derives the geographic features in EPSG:3310, the same projection used in
training.

## Verification

The browser must produce byte-identical predictions to Python, or the whole
exercise is theatre. Two checks run against the 300-listing fixture:

```
npm run verify                     model evaluation
node scripts/verify_features.mjs   feature derivation + end-to-end
```

Current status: **300/300 bit-identical**, and $0.00 end-to-end difference when
features are derived from a raw lat/lon rather than taken from the fixture.

## Deployed model vs. analysis model

The browser runs an 18-feature model (MAPE 12.9%) rather than the 24-feature one
from the notebook (12.6%). The six omitted features are census-tract and ZIP
market averages, which would need roughly 2 MB of extra polygon data to compute
exactly client-side and are worth 0.3 percentage points. Everything kept is
computed exactly as it was in training.

## Geocoding

Address autocomplete matches the dataset locally first (with street-abbreviation
normalisation, so "West Cliff Drive" finds "W Cliff Dr"), then falls back to
[Photon](https://photon.komoot.io) for addresses not in the data. The Census
geocoder would have been the natural choice but sends no CORS headers.
