#!/usr/bin/env python3
"""
D4: derive the modeling feature table from the cleaned listing events.

Adds the geographic features from scripts/geo.py plus a time dimension. The
time index matters: studio/1br median rent moved ~$1,795 -> $2,295 between
2020 and 2026, so a model without it will systematically misprice.

Run:  .venv/bin/python scripts/features.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from geo import add_geo_features  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
EPOCH = pd.Timestamp("2020-01-01")


def main():
    df = pd.read_parquet(PROC / "listings_clean.parquet")
    print(f"loaded {len(df):,} cleaned events")

    g = pd.DataFrame(add_geo_features(df).drop(columns="geometry"))
    print(f"geo features attached: "
          f"{[c for c in g.columns if c.startswith('dist_')]}")

    # --- time -------------------------------------------------------------
    g["listed_year"] = g["listedDate"].dt.year
    g["listed_month"] = g["listedDate"].dt.month
    # Continuous time index; lets the model learn drift instead of memorizing years.
    g["months_since_2020"] = ((g["listedDate"] - EPOCH).dt.days / 30.44).round(2)
    # UCSC/CSUMB lease turnover concentrates in late summer.
    g["is_turnover_season"] = g["listed_month"].isin([7, 8, 9])

    # --- external joins ---------------------------------------------------
    g["month"] = g["listedDate"].dt.to_period("M").astype(str)

    acs = pd.read_csv(PROC.parent / "external/acs_tracts.csv", dtype={"GEOID": str})
    g = g.merge(acs, on="GEOID", how="left")

    zori = pd.read_csv(PROC.parent / "external/zori_zip.csv", dtype={"zipCode": str})
    g = g.merge(zori[["zipCode", "month", "zori"]].rename(columns={"zori": "zori_zip"}),
                on=["zipCode", "month"], how="left")

    # Regional index, forward-filled so listing months past the index end still
    # get a deflator rather than dropping out.
    idx = (pd.read_csv(PROC.parent / "external/zori_index.csv")
             .set_index("month").sort_index())
    full = pd.period_range(idx.index.min(), max(idx.index.max(), g["month"].max()),
                           freq="M").astype(str)
    idx = idx.reindex(full).ffill().rename_axis("month").reset_index()
    g = g.merge(idx, on="month", how="left")

    # --- target and ratios ------------------------------------------------
    g["log_price"] = np.log(g["price"])
    # Rent restated in REF_MONTH dollars, removing market-wide drift. Use this
    # as an alternative target to check that the model is learning property
    # characteristics rather than just the passage of time.
    g["real_price"] = g["price"] * g["deflator_to_ref"]
    g["log_real_price"] = np.log(g["real_price"])
    g["rent_vs_zip_zori"] = g["price"] / g["zori_zip"]
    # Small ZIPs have no ZORI series; flag rather than impute silently.
    g["zori_missing"] = g["zori_zip"].isna()
    g["price_per_sqft"] = (g["price"] / g["squareFootage"]).replace([np.inf], np.nan)
    g["baths_per_bed"] = g["bathrooms"] / g["bedrooms"].clip(lower=1)

    g.to_parquet(PROC / "features.parquet", index=False)
    print(f"\nwrote data/processed/features.parquet  ({len(g):,} rows, {g.shape[1]} cols)")
    ext = ["zori_zip", "deflator_to_ref", "tract_median_hh_income",
           "tract_median_gross_rent", "tract_pct_renter", "tract_pop_density_sqmi"]
    print("external join coverage:")
    for c in ext:
        print(f"    {c:<28} {g[c].notna().mean():.0%}")

    t = g[g.is_studio_1br & g.county.isin(["Santa Cruz", "Monterey"])]
    print(f"\n--- studio/1br modeling slice: {len(t):,} rows ---")

    print("\nSpearman correlation with log(rent), studio/1br:")
    num = ["dist_coast_mi", "dist_university_mi", "dist_ucsc_mi", "dist_hwy17_mi",
           "dist_town_center_mi", "dist_sc_downtown_mi", "squareFootage",
           "bathrooms", "months_since_2020", "yearBuilt", "n_reposts",
           "zori_zip", "tract_median_hh_income", "tract_median_gross_rent",
           "tract_pct_renter", "tract_pop_density_sqmi"]
    corr = (t[num + ["log_price"]].corr(method="spearman")["log_price"]
            .drop("log_price").sort_values())
    for k, v in corr.items():
        bar = "#" * int(abs(v) * 40)
        print(f"  {k:<22} {v:+.3f}  {bar}")

    print("\nstudio/1br median rent by Census place (n>=25):")
    by = (t.groupby(["county", "place"])
            .agg(n=("price", "size"), median=("price", "median"),
                 coast_mi=("dist_coast_mi", "median"))
            .query("n >= 25").sort_values("median", ascending=False))
    print(by.assign(median=by["median"].map("${:,.0f}".format),
                    coast_mi=by["coast_mi"].round(1)).to_string())


if __name__ == "__main__":
    main()
