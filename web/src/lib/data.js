// Loads the exported model bundle and static geography once, at startup.
import { prepareContext } from './features.js';

const BASE = `${import.meta.env.BASE_URL}model/`;

async function json(name) {
  const res = await fetch(BASE + name);
  if (!res.ok) throw new Error(`failed to load ${name}: ${res.status}`);
  return res.json();
}

export async function loadEverything() {
  const [bundle, meta, regionsGeo, countiesGeo, coastGeo, properties] =
    await Promise.all([
      json('trees.json'), json('meta.json'), json('regions.geojson'),
      json('counties.geojson'), json('coastline.geojson'), json('properties.json'),
    ]);
  return {
    bundle,
    meta,
    properties,
    ctx: prepareContext({ meta, regionsGeo, countiesGeo, coastGeo }),
  };
}
