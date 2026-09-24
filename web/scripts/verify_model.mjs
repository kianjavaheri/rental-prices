// Checks the JS port against predictions produced by Python.
// Run: npm run verify
import { readFileSync } from 'fs';
import { predictTrees, encodeRow } from '../src/lib/lgbm.js';

const base = new URL('../public/model/', import.meta.url);
const read = (f) => JSON.parse(readFileSync(new URL(f, base)));

const bundle = read('trees.json');
const meta = read('meta.json');
const fixture = read('fixture.json');
const { intercept, slope } = meta.trend;

let worstLog = 0, worstUsd = 0, exact = 0;

for (const c of fixture) {
  const resid = predictTrees(bundle.trees, encodeRow(bundle, c.features));
  const logPred = intercept + slope * c.features.months_since_2020 + resid;
  const dLog = Math.abs(logPred - c.expected_log);
  const dUsd = Math.abs(Math.exp(logPred) - c.expected_price);
  if (dLog === 0) exact++;
  worstLog = Math.max(worstLog, dLog);
  worstUsd = Math.max(worstUsd, dUsd);
}

console.log(`checked ${fixture.length} listings against Python`);
console.log(`bit-identical:    ${exact}/${fixture.length}`);
console.log(`worst difference: ${worstLog.toExponential(3)} log  /  $${worstUsd.toExponential(3)}`);

if (worstLog < 1e-9) {
  console.log('\nPASS — the JS port reproduces Python');
} else {
  console.log('\nFAIL');
  process.exit(1);
}
