#!/usr/bin/env python3
"""
D1: build the geographic reference layers used for feature derivation.

Downloads two Census TIGER/Line 2025 files (skipped if already present), clips
them to the study area, and writes small GeoJSON layers that are committed:

    data/geo/places.geojson     incorporated cities + CDPs (sub-market polygons)
    data/geo/coastline.geojson  ocean shoreline, for distance-to-coast

Run:  .venv/bin/python scripts/build_geo.py
"""

import urllib.request
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "geo"
SRC = GEO / "source"

TIGER = "https://www2.census.gov/geo/tiger/TIGER2025"
SOURCES = {
    "place": f"{TIGER}/PLACE/tl_2025_06_place.zip",
    "coastline": f"{TIGER}/COASTLINE/tl_2025_us_coastline.zip",
}

# Santa Cruz + Monterey pull circles, with margin. Stops south of SF Bay.
STUDY_BBOX = (-122.40, 36.35, -121.35, 37.35)  # minx, miny, maxx, maxy (lon/lat)


def fetch(name, url):
    out = SRC / url.rsplit("/", 1)[1]
    if not out.exists():
        print(f"downloading {out.name} ...")
        SRC.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, out)
    return out


def main():
    clip = box(*STUDY_BBOX)

    places = gpd.read_file(fetch("place", SOURCES["place"]), bbox=STUDY_BBOX)
    places = places[places.intersects(clip)]
    places = places[["GEOID", "NAME", "NAMELSAD", "CLASSFP", "geometry"]].rename(
        columns={"NAME": "place", "NAMELSAD": "place_full"})
    # CLASSFP C1 = incorporated city; U1/U2 = census designated place
    places["place_kind"] = places["CLASSFP"].map(
        lambda c: "city" if c.startswith("C") else "cdp")
    places = places.drop(columns="CLASSFP").to_crs(4326)
    places.to_file(GEO / "places.geojson", driver="GeoJSON")
    print(f"places.geojson     {len(places):>3} polygons "
          f"({(places.place_kind == 'city').sum()} cities, "
          f"{(places.place_kind == 'cdp').sum()} CDPs)")

    coast = gpd.read_file(fetch("coastline", SOURCES["coastline"]), bbox=STUDY_BBOX)
    coast = gpd.clip(coast.to_crs(4326), clip)[["geometry"]]
    coast.to_file(GEO / "coastline.geojson", driver="GeoJSON")
    n_vertices = sum(len(g.coords) for geom in coast.geometry
                     for g in getattr(geom, "geoms", [geom]))
    print(f"coastline.geojson  {len(coast):>3} line features, {n_vertices} vertices")


if __name__ == "__main__":
    main()
