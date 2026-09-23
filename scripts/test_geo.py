#!/usr/bin/env python3
"""
D1 validation for scripts/geo.py. Run:  .venv/bin/python scripts/test_geo.py

1. Reference points: every hand-coded downtown/campus must fall inside the
   Census place polygon it claims to be in.
2. Ground truth from street names: real listings on streets whose geography is
   unambiguous (West Cliff Dr is on the ocean, Salinas is inland, ...) must get
   plausible feature values.
3. Coverage: no missing distances; place assignment behaves.
"""

import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from geo import (DOWNTOWNS, HWY17_ACCESS, UNIVERSITIES, add_geo_features,  # noqa: E402
                 load_layers)

ROOT = Path(__file__).resolve().parent.parent
failures = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'  -- ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def load_listings():
    recs = []
    for circle in ("santacruz", "montereyco"):
        for f in sorted((ROOT / "data/raw/2026-09-20" / circle).glob("rental_offset*.json")):
            recs += json.loads(f.read_text())["records"]
    df = pd.DataFrame(recs).drop_duplicates("id")
    return df.dropna(subset=["latitude", "longitude"])


layers = load_layers()
places = layers[0]

print("\n1. Reference points fall inside their claimed Census place")
def place_of(lat, lon):
    pt = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs=4326).to_crs(3310).iloc[0]
    hit = places[places.contains(pt)]
    return hit["place"].iloc[0] if len(hit) else "Unincorporated"

for name, ((lat, lon), expected) in DOWNTOWNS.items():
    got = place_of(lat, lon)
    check(f"downtown {name}", got == expected, f"in {got}" if got != expected else "")
check("campus UCSC", place_of(*UNIVERSITIES["UCSC"]) == "Santa Cruz",
      place_of(*UNIVERSITIES["UCSC"]))
csumb = place_of(*UNIVERSITIES["CSUMB"])
check("campus CSUMB", csumb in ("Marina", "Seaside", "Unincorporated"), csumb)
for name, (lat, lon) in HWY17_ACCESS.items():
    got = place_of(lat, lon)
    check(f"hwy17 {name} in Santa Cruz/Scotts Valley/unincorporated",
          got in ("Santa Cruz", "Scotts Valley", "Pasatiempo", "Unincorporated"), got)

print("\n2. Ground truth from street names (real listings)")
df = load_listings()
g = add_geo_features(df, layers)
addr = g["formattedAddress"].str.lower()

def streets(pattern, city=None):
    m = addr.str.contains(pattern, regex=True) if pattern else pd.Series(True, index=g.index)
    if city:
        m &= g["city"].eq(city)
    return g[m]

cases = [
    # (label, subset, column, test, description)
    ("West Cliff Dr is oceanfront",    streets(r"\b(?:w|west) cliff dr", "Santa Cruz"),   "dist_coast_mi", lambda s: s.median() < 0.15, "median < 0.15 mi"),
    ("East Cliff Dr is oceanfront",    streets(r"\b(?:e|east) cliff dr"),                  "dist_coast_mi", lambda s: s.median() < 0.20, "median < 0.20 mi"),
    ("PG Ocean View Blvd oceanfront",  streets(r"ocean view blvd", "Pacific Grove"), "dist_coast_mi", lambda s: s.median() < 0.15, "median < 0.15 mi"),
    ("Salinas is inland",              g[g["city"].eq("Salinas")],                 "dist_coast_mi", lambda s: s.quantile(.05) > 5, "p05 > 5 mi"),
    ("Boulder Creek is inland",        g[g["city"].eq("Boulder Creek")],           "dist_coast_mi", lambda s: s.quantile(.05) > 5, "p05 > 5 mi"),
    # Bay St runs ~1.5 mi from the ocean up to campus, so expect ~1-2.7 mi to campus core.
    ("High St / Bay St near UCSC",     streets(r"\b(?:high st|bay st)\b", "Santa Cruz"), "dist_ucsc_mi", lambda s: s.min() < 1.2 and s.median() < 2.0, "min < 1.2, median < 2.0 mi"),
    ("Scotts Valley near Hwy 17",      g[g["city"].eq("Scotts Valley")],           "dist_hwy17_mi", lambda s: s.median() < 1.5, "median < 1.5 mi"),
    ("Salinas far from Hwy 17",        g[g["city"].eq("Salinas")],                 "dist_hwy17_mi", lambda s: s.min() > 20, "min > 20 mi"),
    ("Pacific Ave SC near downtown",   streets(r"\bpacific ave\b", "Santa Cruz"),  "dist_town_center_mi", lambda s: s.median() < 0.6, "median < 0.6 mi"),
    ("Monterey is far from SC downtown", g[g["city"].eq("Monterey")],          "dist_sc_downtown_mi", lambda s: s.min() > 24, "min > 24 mi (straight line across the bay)"),
    ("Marina near CSUMB",              g[g["city"].eq("Marina")],                  "dist_csumb_mi", lambda s: s.median() < 2.5, "median < 2.5 mi"),
]
for label, sub, col, test, desc in cases:
    if len(sub) == 0:
        check(label, False, "no matching listings")
        continue
    s = sub[col]
    check(label, bool(test(s)),
          f"{desc}; n={len(sub)}, median={s.median():.2f}, range {s.min():.2f}-{s.max():.2f}")

print("\n3. Coverage and place assignment")
dist_cols = [c for c in g.columns if c.startswith("dist_")]
check("tract assigned to every listing", g["GEOID"].notna().all(),
      f"{g['GEOID'].isna().sum()} unassigned")
check("no missing distances", not g[dist_cols].isna().any().any(),
      str(g[dist_cols].isna().sum()[lambda s: s > 0].to_dict()))
live_oak = g[g["city"].eq("Santa Cruz") & g["place"].eq("Live Oak")]
check("Live Oak recovered from 'Santa Cruz' mailing city", len(live_oak) > 50,
      f"{len(live_oak)} listings relabeled")
# Mailing cities legitimately cover adjacent CDPs and unincorporated land
# (Watsonville -> Amesti/Corralitos/Freedom, Salinas -> Prunedale/Boronda).
# What would indicate a bug is a point landing in a *different incorporated city*.
for city in ("Watsonville", "Salinas", "Monterey", "Pacific Grove", "Scotts Valley"):
    sub = g[g["city"].eq(city)]
    other_city = ((sub["place_kind"] == "city") & (sub["place"] != city)).mean()
    check(f"{city}: <3% land in a different incorporated city", other_city < 0.03,
          f"{other_city:.1%} of {len(sub)}; same-city {(sub['place'] == city).mean():.0%}")

print(f"\nplace_kind mix: {g['place_kind'].value_counts().to_dict()}")
print(f"\nfeature summary (n={len(g)}):")
print(g[dist_cols].describe(percentiles=[.05, .5, .95]).T[["min", "5%", "50%", "95%", "max"]]
      .round(2).to_string())

print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} FAILED: {failures}'}")
sys.exit(1 if failures else 0)
