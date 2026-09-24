#!/usr/bin/env python3
"""
Export everything the browser app needs to run the model client-side.

Writes to web/public/model/:
    trees.json        the 600 LightGBM trees, feature order, category vocabularies
    meta.json         trend coefficients, conformal k, medians, reference points
    regions.geojson   simplified place polygons (place, place_kind, county)
    counties.geojson  county outlines, for points outside every place
    coastline.geojson simplified shoreline, for distance-to-ocean
    properties.json   every studio/1BR property: location, attributes, rent history
    fixture.json      50 listings with Python predictions, to verify the JS port

Run:  .venv/bin/python scripts/export_web.py
"""

import json
from pathlib import Path

import sys

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
from shapely.geometry import shape
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).parent))
from geo import UNIVERSITIES, HWY17_ACCESS, DOWNTOWNS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "model"
CUTOFF = pd.Timestamp("2026-01-01")

# The deployed model uses only features the browser can compute EXACTLY from a
# lat/lon: geometry against shipped polygons, plus what the user types. The five
# lookup features (zori_zip, tract_*) would need ZIP and tract polygons -- ~2 MB
# of extra payload -- and are worth 0.3 MAPE points, so they are left out.
#   full model (notebook): 24 features, MAE $295, MAPE 12.6%
#   web model (deployed):  18 features, MAE $297, MAPE 12.9%
NUMERIC = ["bedrooms", "bathrooms", "squareFootage", "dist_coast_mi", "dist_ucsc_mi",
           "dist_csumb_mi", "dist_hwy17_mi", "dist_town_center_mi", "dist_sc_downtown_mi",
           "latitude", "longitude", "months_since_2020", "listed_month", "sqft_missing"]
CATEGORICAL = ["place", "propertyType", "place_kind", "county"]
FEATURES = NUMERIC + CATEGORICAL
PARAMS = dict(n_estimators=600, learning_rate=0.05, num_leaves=31,
              min_child_samples=20, random_state=42, verbose=-1)


def load_split():
    df = pd.read_parquet(ROOT / "data/processed/features.parquet")
    t = df[df.is_studio_1br & df.county.isin(["Santa Cruz", "Monterey"])].copy()
    t["coord"] = t.latitude.round(5).astype(str) + "," + t.longitude.round(5).astype(str)
    train, test = t[t.listedDate < CUTOFF], t[t.listedDate >= CUTOFF].copy()
    train = train[~train.coord.isin(set(train.coord) & set(test.coord))].copy()
    return t, train, test


def as_lgb(d, categories=None):
    X = d[FEATURES].copy()
    for c in CATEGORICAL:
        X[c] = X[c].astype("category")
        if categories is not None:
            X[c] = X[c].cat.set_categories(categories[c])
    return X


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t, train, test = load_split()

    X_train = as_lgb(train)
    cats = {c: list(X_train[c].cat.categories) for c in CATEGORICAL}
    X_test = as_lgb(test, cats)

    trend = LinearRegression().fit(train[["months_since_2020"]], train["log_price"])
    resid = train["log_price"] - trend.predict(train[["months_since_2020"]])
    model = lgb.LGBMRegressor(**PARAMS).fit(X_train, resid)

    # ---- conformal half-width, from a held-out recent slice of train ----------
    cut = train["months_since_2020"].quantile(0.80)
    fit_d, cal_d = train[train.months_since_2020 < cut], train[train.months_since_2020 >= cut]
    tr_tmp = LinearRegression().fit(fit_d[["months_since_2020"]], fit_d["log_price"])
    m_tmp = lgb.LGBMRegressor(**PARAMS).fit(
        as_lgb(fit_d, cats), fit_d["log_price"] - tr_tmp.predict(fit_d[["months_since_2020"]]))
    cal_pred = tr_tmp.predict(cal_d[["months_since_2020"]]) + m_tmp.predict(as_lgb(cal_d, cats))
    k = float(np.quantile(np.abs(cal_d["log_price"] - cal_pred), 0.80))

    # ---- trees ---------------------------------------------------------------
    dump = model.booster_.dump_model()
    trees = [ti["tree_structure"] for ti in dump["tree_info"]]

    def prune(n):
        """Drop the bookkeeping fields the browser doesn't need."""
        if "leaf_value" in n and "split_index" not in n:
            # full precision: rounding here accumulates across 600 trees
            return {"v": n["leaf_value"]}
        out = {"f": n["split_feature"], "t": n["threshold"],
               "d": 0 if n["decision_type"] == "<=" else 1,
               "l": bool(n["default_left"]),
               "m": {"None": 0, "Zero": 1, "NaN": 2}[n["missing_type"]]}
        if out["d"] == 0:
            # a rounded threshold can flip a decision for a value sitting on it
            out["t"] = float(out["t"])
        out["L"], out["R"] = prune(n["left_child"]), prune(n["right_child"])
        return out

    (OUT / "trees.json").write_text(json.dumps({
        "features": FEATURES, "numeric": NUMERIC, "categorical": CATEGORICAL,
        "categories": cats, "trees": [prune(x) for x in trees],
    }, separators=(",", ":")))

    # ---- geography -----------------------------------------------------------
    places = gpd.read_file(ROOT / "data/geo/places.geojson")
    tracts = gpd.read_file(ROOT / "data/geo/tracts.geojson").to_crs(4326)
    counties = tracts.dissolve(by="COUNTYFP").reset_index()
    counties["county"] = counties["COUNTYFP"].map({"087": "Santa Cruz", "053": "Monterey"})
    # tag each place polygon with the county it sits in
    # tag by the polygon's representative point, so a place touching a county
    # border is not assigned to the wrong side
    reps = places.copy()
    reps["geometry"] = places.geometry.representative_point()
    tagged = gpd.sjoin(reps, counties[["county", "geometry"]], how="left", predicate="within")
    places["county"] = tagged[~tagged.index.duplicated(keep="first")]["county"]
    places["county"] = places["county"].fillna("Santa Cruz")
    places["geometry"] = places.geometry.simplify(0.00002)
    places[["place", "place_kind", "county", "geometry"]].to_file(
        OUT / "regions.geojson", driver="GeoJSON")

    # unincorporated points fall outside every place polygon but still need a county
    counties["geometry"] = counties.geometry.simplify(0.0005)
    counties[["county", "geometry"]].to_file(OUT / "counties.geojson", driver="GeoJSON")

    # NOT simplified -- training distances came from the full geometry
    gpd.read_file(ROOT / "data/geo/coastline.geojson")[["geometry"]].to_file(
        OUT / "coastline.geojson", driver="GeoJSON")

    # ---- properties for the map, autocomplete and comparables ----------------
    props = []
    for pid, g in t.sort_values("listedDate").groupby("id"):
        f = g.iloc[-1]
        props.append({
            "id": pid,
            "addr": f.formattedAddress,
            "lat": round(float(f.latitude), 5),
            "lon": round(float(f.longitude), 5),
            "place": f.place,
            "beds": int(f.bedrooms),
            "baths": None if pd.isna(f.bathrooms) else float(f.bathrooms),
            "sqft": None if pd.isna(f.squareFootage) else int(f.squareFootage),
            "type": f.propertyType,
            "listings": [{"d": d.listedDate.strftime("%Y-%m"), "p": int(d.price)}
                         for d in g.itertuples()],
        })
    (OUT / "properties.json").write_text(json.dumps(props, separators=(",", ":")))

    # ---- meta ----------------------------------------------------------------
    (OUT / "meta.json").write_text(json.dumps({
        "trend": {"intercept": float(trend.intercept_), "slope": float(trend.coef_[0])},
        "k": k,
        "epoch": "2020-01-01",
        "medians": {c: (None if pd.isna(v) else float(v))
                    for c, v in train[NUMERIC].median().items()},
        "trainRange": {"minMonths": float(train.months_since_2020.min()),
                       "maxMonths": float(train.months_since_2020.max())},
        "metrics": {"mae": 297, "mape": 12.9, "coverage": 0.796,
                    "n_train": len(train), "n_test": len(test),
                    "fullModel": {"mae": 295, "mape": 12.6, "coverage": 0.812,
                                  "note": "notebook model, 24 features"}},
        "points": {
            "universities": {k: list(v) for k, v in UNIVERSITIES.items()},
            "hwy17": {k: list(v) for k, v in HWY17_ACCESS.items()},
            "downtowns": {k: list(v[0]) for k, v in DOWNTOWNS.items()},
            "scDowntown": list(DOWNTOWNS["Santa Cruz"][0]),
        },
    }, indent=2))

    # ---- verification fixture -----------------------------------------------
    samp = test.sample(300, random_state=7)
    pl = trend.predict(samp[["months_since_2020"]]) + model.predict(as_lgb(samp, cats))
    (OUT / "fixture.json").write_text(json.dumps([
        {"features": {c: (None if pd.isna(r[c]) else
                          (r[c] if c in CATEGORICAL else float(r[c]))) for c in FEATURES},
         "date": r["listedDate"].strftime("%Y-%m-%d"),
         "expected_log": float(p), "expected_price": float(np.exp(p))}
        for (_, r), p in zip(samp.iterrows(), pl)
    ], indent=2))

    for f in sorted(OUT.iterdir()):
        print(f"   {f.name:<22}{f.stat().st_size/1e6:>7.2f} MB")
    print(f"\n   k={k:.4f}   trend slope={trend.coef_[0]:.6f}   properties={len(props):,}")


if __name__ == "__main__":
    main()
