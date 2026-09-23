#!/usr/bin/env python3
"""
D3: turn the raw RentCast cache into a clean listing-EVENT table.

RentCast's `id` is address-derived, so one record == one property, and the
`history` object holds that property's past rental listings. We expand history
into events, then collapse re-posting churn: a landlord who relists the same
unit at the same price every few weeks produces many near-identical entries
(one unit in the data has 9, all at $3,950 with daysOnMarket=1). Genuine
re-rentals years later at a different price are kept.

Every filter is logged with its row count -- that table belongs in the writeup.

Run:  .venv/bin/python scripts/clean.py
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = "2026-09-20"
OUT = ROOT / "data" / "processed"

CHURN_DAYS = 120          # same price within this window == a repost, not a re-rental
PRICE_MIN, PRICE_MAX = 400, 20_000
COORD_SPREAD_MI = 1.0     # same street address geocoded further apart than this = bad

PROP_COLS = ["id", "formattedAddress", "addressLine1", "addressLine2", "city",
             "zipCode", "county", "latitude", "longitude", "propertyType",
             "bedrooms", "bathrooms", "squareFootage", "yearBuilt", "status"]

CITY_FIXES = {"Carmel By The Sea": "Carmel-by-the-Sea",
              "Carmel-By-The-Sea": "Carmel-by-the-Sea",
              "Carmel": "Carmel-by-the-Sea"}

log = []


def note(step, df, extra=""):
    log.append((step, len(df), extra))
    print(f"  {step:<52} {len(df):>7,}  {extra}")


def load_raw():
    recs = []
    for circle in ("santacruz", "montereyco"):
        for f in sorted((ROOT / "data/raw" / SNAPSHOT / circle).glob("rental_offset*.json")):
            recs += json.loads(f.read_text())["records"]
    return recs


def to_events(recs):
    """One row per (property, listing event)."""
    rows = []
    for r in recs:
        prop = {k: r.get(k) for k in PROP_COLS}
        hist = r.get("history") or {}
        events = [v for v in hist.values() if v.get("event") == "Rental Listing"]
        if not events:                      # no history: use the top-level listing
            events = [{"price": r.get("price"), "listedDate": r.get("listedDate"),
                       "removedDate": r.get("removedDate"),
                       "daysOnMarket": r.get("daysOnMarket"),
                       "listingType": r.get("listingType")}]
        for e in events:
            rows.append({**prop,
                         "price": e.get("price"),
                         "listedDate": e.get("listedDate"),
                         "removedDate": e.get("removedDate"),
                         "daysOnMarket": e.get("daysOnMarket"),
                         "listingType": e.get("listingType")})
    df = pd.DataFrame(rows)
    for c in ("listedDate", "removedDate"):
        df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_localize(None)
    return df


def collapse_churn(df):
    """Merge same-price events for the same property within CHURN_DAYS."""
    df = df.sort_values(["id", "listedDate"]).reset_index(drop=True)
    gap = df.groupby("id", sort=False)["listedDate"].diff().dt.days
    same_price = df["price"].eq(df.groupby("id", sort=False)["price"].shift())
    new_event = ~(same_price & gap.le(CHURN_DAYS))
    df["_grp"] = new_event.groupby(df["id"]).cumsum()

    agg = (df.groupby(["id", "_grp"], sort=False)
             .agg(**{c: (c, "first") for c in PROP_COLS if c != "id"},
                  price=("price", "first"),
                  listedDate=("listedDate", "first"),
                  removedDate=("removedDate", "last"),
                  daysOnMarket=("daysOnMarket", "max"),
                  listingType=("listingType", "first"),
                  n_reposts=("price", "size"))
             .reset_index().drop(columns="_grp"))
    return agg


def main():
    recs = load_raw()
    print(f"\nraw records loaded: {len(recs):,}")
    recs = list({r["id"]: r for r in recs}.values())
    print(f"after dedup on property id: {len(recs):,}\n")

    print("listing events")
    df = to_events(recs)
    note("expanded from history", df)
    df = collapse_churn(df)
    note("after collapsing repost churn", df,
         f"max reposts merged: {int(df.n_reposts.max())}")

    print("\nfilters")
    for col in ("price", "listedDate", "bedrooms", "latitude", "longitude", "propertyType"):
        before = len(df)
        df = df[df[col].notna()]
        if before != len(df):
            note(f"drop missing {col}", df, f"-{before - len(df):,}")

    before = len(df)
    df = df[df["price"].between(PRICE_MIN, PRICE_MAX)]
    note(f"drop price outside ${PRICE_MIN}-${PRICE_MAX:,}", df, f"-{before - len(df):,}")

    # Same street address geocoded far apart => at least one point is wrong.
    key = df["addressLine1"].str.lower().str.strip() + "|" + df["city"].str.lower()
    spread = df.assign(k=key).groupby("k")[["latitude", "longitude"]].transform(
        lambda s: s.max() - s.min())
    bad = (spread["latitude"] * 69.05 > COORD_SPREAD_MI) | \
          (spread["longitude"] * 55.2 > COORD_SPREAD_MI)
    before = len(df)
    df = df[~bad]
    note(f"drop inconsistent coords for same address", df, f"-{before - len(df):,}")

    df["city"] = df["city"].replace(CITY_FIXES)
    df["sqft_missing"] = df["squareFootage"].isna()
    df["is_studio_1br"] = df["bedrooms"].isin([0, 1])

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "listings_clean.parquet", index=False)
    pd.DataFrame(log, columns=["step", "rows", "note"]).to_csv(
        OUT / "clean_filter_log.csv", index=False)

    print(f"\nwrote data/processed/listings_clean.parquet  ({len(df):,} rows)")
    print(f"\ncounty:    {df.county.value_counts().head(4).to_dict()}")
    print(f"studio/1br: {int(df.is_studio_1br.sum()):,}  "
          f"({df.is_studio_1br.mean():.1%})")
    print(f"sqft missing: {df.sqft_missing.mean():.1%}")
    print(f"\nlisting events per year:")
    print(df.listedDate.dt.year.value_counts().sort_index().to_string())
    t = df[df.is_studio_1br]
    print(f"\nstudio/1br median rent by year:")
    print(t.groupby(t.listedDate.dt.year)["price"].agg(["size", "median"]).to_string())


if __name__ == "__main__":
    main()
