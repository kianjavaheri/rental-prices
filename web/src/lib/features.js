// Builds the 24-feature row the model expects from a user's inputs.
// Mirrors scripts/geo.py + scripts/features.py so browser values match training.

import {
  buildCoastline, buildRegions, distanceToCoastMiles, findRegion,
  minMilesToPoints, milesToPoint,
} from './geo.js';

const EPOCH = Date.UTC(2020, 0, 1);
const DAYS_PER_MONTH = 30.44;

export function monthsSince2020(date) {
  const days = (date.getTime() - EPOCH) / 86400000;
  return Math.round((days / DAYS_PER_MONTH) * 100) / 100;   // features.py rounds to 2dp
}

/** One-time preparation of the static layers. */
export function prepareContext({ meta, regionsGeo, countiesGeo, coastGeo }) {
  return {
    meta,
    regions: buildRegions(regionsGeo),
    counties: buildRegions(countiesGeo),
    coast: buildCoastline(coastGeo),
    universities: Object.values(meta.points.universities),
    hwy17: Object.values(meta.points.hwy17),
    downtowns: Object.values(meta.points.downtowns),
    ucsc: meta.points.universities.UCSC,
    csumb: meta.points.universities.CSUMB,
    scDowntown: meta.points.scDowntown,
  };
}

/**
 * @param ctx      from prepareContext
 * @param input    { lat, lon, bedrooms, bathrooms, squareFootage, propertyType, date }
 * @returns        { features, derived } — derived holds what we looked up, for the UI
 */
export function buildFeatures(ctx, input) {
  const { lat, lon } = input;

  const region = findRegion(ctx.regions, lon, lat);
  const place = region?.place ?? 'Unincorporated';
  const placeKind = region?.place_kind ?? 'unincorporated';
  const county = region?.county ?? nearestCounty(ctx, lon, lat);

  const sqft = input.squareFootage === '' || input.squareFootage == null
    ? null : Number(input.squareFootage);

  const features = {
    bedrooms: Number(input.bedrooms),
    bathrooms: input.bathrooms == null || input.bathrooms === ''
      ? null : Number(input.bathrooms),
    squareFootage: sqft,
    dist_coast_mi: distanceToCoastMiles(ctx.coast, lon, lat),
    dist_ucsc_mi: milesToPoint(ctx.ucsc, lon, lat),
    dist_csumb_mi: milesToPoint(ctx.csumb, lon, lat),
    dist_hwy17_mi: minMilesToPoints(ctx.hwy17, lon, lat),
    dist_town_center_mi: minMilesToPoints(ctx.downtowns, lon, lat),
    dist_sc_downtown_mi: milesToPoint(ctx.scDowntown, lon, lat),
    latitude: lat,
    longitude: lon,
    months_since_2020: monthsSince2020(input.date),
    listed_month: input.date.getUTCMonth() + 1,
    sqft_missing: sqft == null ? 1 : 0,
    place,
    propertyType: input.propertyType ?? 'Apartment',
    place_kind: placeKind,
    county,
  };

  return {
    features,
    derived: { place, placeKind, county,
               distCoast: features.dist_coast_mi, distUcsc: features.dist_ucsc_mi },
  };
}

// Points outside every place polygon (unincorporated land) still need a county.
function nearestCounty(ctx, lon, lat) {
  return findRegion(ctx.counties, lon, lat)?.county ?? 'Santa Cruz';
}
