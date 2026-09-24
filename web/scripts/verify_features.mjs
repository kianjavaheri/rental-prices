// Derives features in the browser's way and compares them to Python's values.
// Run: node scripts/verify_features.mjs
import { readFileSync } from 'fs';
import { prepareContext, buildFeatures } from '../src/lib/features.js';
import { predict } from '../src/lib/predict.js';

const base = new URL('../public/model/', import.meta.url);
const read = (f) => JSON.parse(readFileSync(new URL(f, base)));

const bundle = read('trees.json');
const meta = read('meta.json');
const fixture = read('fixture.json');
const ctx = prepareContext({
  meta, regionsGeo: read('regions.geojson'), countiesGeo: read('counties.geojson'),
  coastGeo: read('coastline.geojson'),
});

const GEO = ['dist_coast_mi', 'dist_ucsc_mi', 'dist_csumb_mi', 'dist_hwy17_mi',
             'dist_town_center_mi', 'dist_sc_downtown_mi'];
const LOOKUP = [];
const CATS = ['place', 'place_kind', 'county'];

const diffs = {}, mismatch = {};
let worstUsd = 0, sumAbsUsd = 0;

for (const c of fixture) {
  const f = c.features;
  const { features } = buildFeatures(ctx, {
    lat: f.latitude, lon: f.longitude, bedrooms: f.bedrooms, bathrooms: f.bathrooms,
    squareFootage: f.squareFootage, propertyType: f.propertyType,
    date: new Date(c.date + 'T00:00:00Z'),
  });

  for (const k of [...GEO, ...LOOKUP]) {
    if (f[k] == null || features[k] == null) continue;
    const rel = Math.abs(features[k] - f[k]) / Math.max(1e-9, Math.abs(f[k]));
    diffs[k] = Math.max(diffs[k] ?? 0, rel);
  }
  for (const k of CATS) {
    if (features[k] !== f[k]) {
      mismatch[k] = (mismatch[k] ?? []);
      if (mismatch[k].length < 3) mismatch[k].push(`${f[k]} -> ${features[k]}`);
    }
  }

  const jsPred = predict(ctx, bundle, {
    lat: f.latitude, lon: f.longitude, bedrooms: f.bedrooms, bathrooms: f.bathrooms,
    squareFootage: f.squareFootage, propertyType: f.propertyType,
    date: new Date(c.date + 'T00:00:00Z'),
  });
  const d = Math.abs(jsPred.mid - c.expected_price);
  worstUsd = Math.max(worstUsd, d); sumAbsUsd += d;
}

console.log('GEOMETRY — max relative error vs Python (should be ~0):');
for (const k of GEO) console.log(`   ${k.padEnd(24)}${(diffs[k] ?? 0).toExponential(2)}`);
console.log('\nCATEGORICALS:');
for (const k of CATS) {
  const m = mismatch[k];
  console.log(`   ${k.padEnd(24)}${m ? `${m.length}+ mismatches e.g. ${m[0]}` : 'all match'}`);
}
console.log(`\nEND-TO-END PREDICTION (browser-derived features vs Python):`);
console.log(`   mean |difference|  $${(sumAbsUsd / fixture.length).toFixed(2)}`);
console.log(`   worst  difference  $${worstUsd.toFixed(2)}`);
