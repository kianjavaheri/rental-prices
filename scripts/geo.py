"""
Geographic feature derivation for listings.

    from geo import add_geo_features
    gdf = add_geo_features(df)   # df needs latitude / longitude columns

All distances are computed in California Albers (EPSG:3310, meters) and
reported in miles. Reference layers come from scripts/build_geo.py.

Hand-coded reference points are approximate (roughly +/- 300 m), which is fine
for mile-scale features. Downtown and campus points are validated against the
Census place polygons by scripts/test_geo.py.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "geo"
CRS_M = 3310            # California Albers, meters
M_PER_MI = 1609.344

# (lat, lon). Each downtown's expected Census place is noted for validation.
UNIVERSITIES = {
    "UCSC":  (36.9916, -122.0583),   # Santa Cruz
    "CSUMB": (36.6540, -121.7985),   # Marina / unincorporated
}

# Silicon Valley commute proxy: Hwy 17 access points on the Santa Cruz side.
HWY17_ACCESS = {
    "Hwy 1/17 interchange": (36.9905, -122.0155),
    "Pasatiempo":           (37.0000, -122.0240),
    "Granite Creek Rd":     (37.0415, -122.0185),
    "Mt Hermon Rd":         (37.0510, -122.0150),
}

DOWNTOWNS = {
    # name:                ((lat, lon),            expected Census place)
    "Santa Cruz":          ((36.9745, -122.0265), "Santa Cruz"),
    "Capitola Village":    ((36.9722, -121.9530), "Capitola"),
    "Soquel Village":      ((36.9880, -121.9560), "Soquel"),
    "Aptos Village":       ((36.9772, -121.9025), "Aptos"),
    "Scotts Valley":       ((37.0510, -122.0130), "Scotts Valley"),
    "Felton":              ((37.0515, -122.0730), "Felton"),
    "Ben Lomond":          ((37.0890, -122.0860), "Ben Lomond"),
    "Boulder Creek":       ((37.1260, -122.1220), "Boulder Creek"),
    "Watsonville":         ((36.9100, -121.7570), "Watsonville"),
    "Monterey":            ((36.6000, -121.8940), "Monterey"),
    "Pacific Grove":       ((36.6200, -121.9190), "Pacific Grove"),
    "Carmel-by-the-Sea":   ((36.5550, -121.9230), "Carmel-by-the-Sea"),
    "Seaside":             ((36.6118, -121.8440), "Seaside"),   # Broadway & Fremont
    "Sand City":           ((36.6170, -121.8480), "Sand City"),
    "Marina":              ((36.6840, -121.8020), "Marina"),
    "Salinas":             ((36.6750, -121.6550), "Salinas"),
    "Carmel Valley Village": ((36.4800, -121.7320), "Carmel Valley Village"),
}


def _pts(coords):
    """{name: (lat, lon)} -> GeoSeries in meters."""
    return gpd.GeoSeries([Point(lon, lat) for lat, lon in coords.values()],
                         index=list(coords), crs=4326).to_crs(CRS_M)


def load_layers():
    places = gpd.read_file(GEO / "places.geojson").to_crs(CRS_M)
    coast = gpd.read_file(GEO / "coastline.geojson").to_crs(CRS_M)
    tracts = gpd.read_file(GEO / "tracts.geojson").to_crs(CRS_M)
    return places, coast.geometry.union_all(), tracts


def _nearest_mi(points, refs):
    """Distance in miles from each point to its nearest reference point,
    plus that reference's name."""
    d = pd.DataFrame({name: points.distance(geom) for name, geom in refs.items()})
    return d.min(axis=1) / M_PER_MI, d.idxmin(axis=1)


def add_geo_features(df, layers=None):
    places, coastline, tracts = layers or load_layers()
    gdf = gpd.GeoDataFrame(
        df.copy(), crs=4326,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"])).to_crs(CRS_M)

    # Sub-market: the Census place containing the point. This is better than
    # the listing's mailing city, which labels Live Oak as "Santa Cruz" and
    # blurs Soquel/Aptos/Capitola. Unmatched points are unincorporated land.
    joined = gpd.sjoin(gdf[["geometry"]], places[["place", "place_kind", "geometry"]],
                       how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    gdf["place"] = joined["place"].fillna("Unincorporated")
    gdf["place_kind"] = joined["place_kind"].fillna("unincorporated")

    gdf["dist_coast_mi"] = gdf.geometry.distance(coastline) / M_PER_MI

    uni = _pts(UNIVERSITIES)
    gdf["dist_ucsc_mi"] = gdf.geometry.distance(uni["UCSC"]) / M_PER_MI
    gdf["dist_csumb_mi"] = gdf.geometry.distance(uni["CSUMB"]) / M_PER_MI
    gdf["dist_university_mi"] = gdf[["dist_ucsc_mi", "dist_csumb_mi"]].min(axis=1)

    gdf["dist_hwy17_mi"], _ = _nearest_mi(gdf.geometry, _pts(HWY17_ACCESS))

    # Distance to the nearest town center measures WITHIN-town centrality only:
    # every town has one, so a Salinas listing and a Santa Cruz listing both
    # score "central". Which town it is comes from `place`; absolute position in
    # the regional market comes from dist_sc_downtown_mi below.
    downtowns = _pts({k: v[0] for k, v in DOWNTOWNS.items()})
    gdf["dist_town_center_mi"], gdf["nearest_town_center"] = _nearest_mi(
        gdf.geometry, downtowns)
    gdf["dist_sc_downtown_mi"] = (
        gdf.geometry.distance(downtowns["Santa Cruz"]) / M_PER_MI)

    # Census tract, for the ACS joins in features.py
    tr = gpd.sjoin(gdf[["geometry"]], tracts[["GEOID", "geometry"]],
                   how="left", predicate="within")
    gdf["GEOID"] = tr[~tr.index.duplicated(keep="first")]["GEOID"]

    return gdf.to_crs(4326)
