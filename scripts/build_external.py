#!/usr/bin/env python3
"""
Build the external reference data: Zillow ZORI and Census ACS tract measures.

Outputs (all committed; source archives stay gitignored):
    data/external/zori_zip.csv     monthly ZORI for study-area ZIPs
    data/external/zori_index.csv   regional monthly index, for deflating rents
    data/external/acs_tracts.csv   ACS 5-year tract measures
    data/geo/tracts.geojson        tract polygons, clipped to the study area

Run:  .venv/bin/python scripts/build_external.py
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parent.parent
GEO, EXT, SRC = ROOT / "data/geo", ROOT / "data/external", ROOT / "data/geo/source"

ZORI_URL = ("https://files.zillowstatic.com/research/public_csvs/zori/"
            "Zip_zori_uc_sfrcondomfr_sm_month.csv")
TRACT_URL = "https://www2.census.gov/geo/tiger/TIGER2025/TRACT/tl_2025_06_tract.zip"
STUDY_BBOX = (-122.40, 36.35, -121.35, 37.35)
COUNTIES = {"087": "Santa Cruz", "053": "Monterey", "085": "Santa Clara"}

ACS_YEAR = 2024
ACS_VARS = {                       # ACS 5-year table -> our column name
    "B19013_001E": "tract_median_hh_income",
    "B01003_001E": "tract_population",
    "B25064_001E": "tract_median_gross_rent",
    "B25003_001E": "_occupied_units",
    "B25003_003E": "_renter_occupied",
}
REF_MONTH = "2026-01"              # rents get deflated to this month


def fetch(url):
    out = SRC / url.rsplit("/", 1)[1]
    if not out.exists():
        print(f"downloading {out.name} ...")
        SRC.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, out)
    return out


def api_key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("CENSUS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("CENSUS_API_KEY missing from .env")


def build_zori(zips):
    z = pd.read_csv(fetch(ZORI_URL), dtype={"RegionName": str})
    z = z[z["RegionName"].isin(zips)]
    months = [c for c in z.columns if c[:4].isdigit()]
    long = (z.melt(id_vars=["RegionName", "CountyName"], value_vars=months,
                   var_name="month", value_name="zori")
              .rename(columns={"RegionName": "zipCode"}).dropna(subset=["zori"]))
    long["month"] = pd.to_datetime(long["month"]).dt.to_period("M").astype(str)
    long.to_csv(EXT / "zori_zip.csv", index=False)
    print(f"zori_zip.csv       {long.zipCode.nunique()} ZIPs, "
          f"{long.month.min()}..{long.month.max()}, {len(long):,} rows")

    # Regional index: median across study ZIPs each month, rebased to REF_MONTH.
    idx = long.groupby("month")["zori"].median().rename("zori_region").to_frame()
    idx["deflator_to_ref"] = idx.loc[REF_MONTH, "zori_region"] / idx["zori_region"]
    idx.reset_index().to_csv(EXT / "zori_index.csv", index=False)
    print(f"zori_index.csv     rebased to {REF_MONTH}; "
          f"2020-01 deflator={idx.loc['2020-01','deflator_to_ref']:.3f}")


def build_tracts():
    t = gpd.read_file(fetch(TRACT_URL), bbox=STUDY_BBOX)
    t = t[t.intersects(box(*STUDY_BBOX)) & t["COUNTYFP"].isin(COUNTIES)]
    t = t[["GEOID", "COUNTYFP", "ALAND", "geometry"]].to_crs(4326)
    t.to_file(GEO / "tracts.geojson", driver="GeoJSON")
    print(f"tracts.geojson     {len(t)} tracts")
    return t


def build_acs(tracts):
    key, frames = api_key(), []
    for fips in COUNTIES:
        q = urllib.parse.urlencode({
            "get": "NAME," + ",".join(ACS_VARS),
            "for": "tract:*", "in": f"state:06 county:{fips}", "key": key})
        with urllib.request.urlopen(f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5?{q}") as r:
            rows = json.loads(r.read().decode())
        frames.append(pd.DataFrame(rows[1:], columns=rows[0]))
    a = pd.concat(frames, ignore_index=True)
    a["GEOID"] = a["state"] + a["county"] + a["tract"]
    a = a.rename(columns=ACS_VARS)
    for c in ACS_VARS.values():
        a[c] = pd.to_numeric(a[c], errors="coerce")
        a.loc[a[c] < 0, c] = pd.NA          # ACS uses large negatives for suppressed
    a["tract_pct_renter"] = a["_renter_occupied"] / a["_occupied_units"]

    land = tracts.set_index("GEOID")["ALAND"]
    a["tract_pop_density_sqmi"] = (
        a["tract_population"] / (a["GEOID"].map(land) / 2_589_988.11))

    keep = ["GEOID", "tract_median_hh_income", "tract_median_gross_rent",
            "tract_pct_renter", "tract_pop_density_sqmi", "tract_population"]
    a[keep].to_csv(EXT / "acs_tracts.csv", index=False)
    cov = a[keep].notna().mean().drop("GEOID")
    print(f"acs_tracts.csv     {len(a)} tracts (ACS {ACS_YEAR} 5-year)")
    for k, v in cov.items():
        print(f"    {k:<28} {v:.0%} populated")


def main():
    EXT.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(ROOT / "data/processed/listings_clean.parquet")
    build_zori(set(df["zipCode"].dropna().astype(str)))
    build_acs(build_tracts())


if __name__ == "__main__":
    main()
