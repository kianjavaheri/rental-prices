// Geographic feature derivation, mirroring scripts/geo.py.
// Distances are computed in EPSG:3310 (California Albers, metres) so they match
// the values the model was trained on.

import proj4 from 'proj4';

proj4.defs('EPSG:3310',
  '+proj=aea +lat_0=0 +lon_0=-120 +lat_1=34 +lat_2=40.5 +x_0=0 +y_0=-4000000 ' +
  '+datum=NAD83 +units=m +no_defs');

const M_PER_MI = 1609.344;

/** [lon, lat] -> [x, y] in metres */
export function toAlbers(lon, lat) {
  return proj4('EPSG:4326', 'EPSG:3310', [lon, lat]);
}

export function milesBetween(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]) / M_PER_MI;
}

/** Shortest distance in miles from a projected point to a projected segment. */
function pointToSegment(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  let t = len2 === 0 ? 0 : ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** Flatten a GeoJSON LineString / MultiLineString FeatureCollection, projected. */
export function buildCoastline(geojson) {
  const lines = [];
  for (const f of geojson.features) {
    const g = f.geometry;
    const parts = g.type === 'MultiLineString' ? g.coordinates : [g.coordinates];
    for (const part of parts) lines.push(part.map(([lon, lat]) => toAlbers(lon, lat)));
  }
  return lines;
}

export function distanceToCoastMiles(lines, lon, lat) {
  const p = toAlbers(lon, lat);
  let best = Infinity;
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const d = pointToSegment(p, line[i - 1], line[i]);
      if (d < best) best = d;
    }
  }
  return best / M_PER_MI;
}

// ---------------------------------------------------------------- polygons --

function inRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) &&
        lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function inPolygon(lon, lat, poly) {
  if (!inRing(lon, lat, poly[0])) return false;
  for (let h = 1; h < poly.length; h++) if (inRing(lon, lat, poly[h])) return false;
  return true;                                   // inside outer ring, not in a hole
}

/** Pre-compute bounding boxes so we only test polygons that could match. */
export function buildRegions(geojson) {
  return geojson.features.map((f) => {
    const polys = f.geometry.type === 'MultiPolygon'
      ? f.geometry.coordinates : [f.geometry.coordinates];
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const poly of polys) for (const [x, y] of poly[0]) {
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    }
    return { props: f.properties, polys, bbox: [minX, minY, maxX, maxY] };
  });
}

export function findRegion(regions, lon, lat) {
  for (const r of regions) {
    const [minX, minY, maxX, maxY] = r.bbox;
    if (lon < minX || lon > maxX || lat < minY || lat > maxY) continue;
    for (const poly of r.polys) if (inPolygon(lon, lat, poly)) return r.props;
  }
  return null;
}

// ----------------------------------------------------------- point helpers --

/** Nearest entry in a [{lat, lon, ...}] table, by projected distance. */
export function nearest(table, lon, lat) {
  const p = toAlbers(lon, lat);
  let best = null, bestD = Infinity;
  for (const row of table) {
    const d = Math.hypot(p[0] - row._x, p[1] - row._y);
    if (d < bestD) { bestD = d; best = row; }
  }
  return best;
}

/** Attach projected coordinates once, so `nearest` stays cheap. */
export function projectTable(table) {
  for (const row of table) {
    const [x, y] = toAlbers(row.lon, row.lat);
    row._x = x; row._y = y;
  }
  return table;
}

export function minMilesToPoints(points, lon, lat) {
  const p = toAlbers(lon, lat);
  let best = Infinity;
  for (const [plat, plon] of points) {
    const q = toAlbers(plon, plat);
    best = Math.min(best, Math.hypot(p[0] - q[0], p[1] - q[1]));
  }
  return best / M_PER_MI;
}

export function milesToPoint(point, lon, lat) {
  const [plat, plon] = point;
  return milesBetween(toAlbers(lon, lat), toAlbers(plon, plat));
}
