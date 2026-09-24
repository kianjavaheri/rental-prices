// Minimal LightGBM tree evaluator, ported to match the C++ decision logic exactly.
// Verified against 50 Python predictions by scripts/verify_model.mjs.

const ZERO = 1e-35;

// missing_type codes from the exporter: 0 = None, 1 = Zero, 2 = NaN
function goLeft(node, value) {
  if (node.d === 1) return categoricalLeft(node, value);
  return numericLeft(node, value);
}

function numericLeft(node, value) {
  let v = value;
  const missing = v === null || v === undefined || Number.isNaN(v);

  // LightGBM converts NaN to 0 unless the split was built to handle NaN
  if (missing && node.m !== 2) v = 0;

  if ((node.m === 1 && Math.abs(v) <= ZERO) || (node.m === 2 && missing)) {
    return node.l;                       // default_left
  }
  return v <= node.t;
}

function categoricalLeft(node, value) {
  // value is the integer category code, or null when the category is unknown
  if (value === null || value === undefined || Number.isNaN(value)) return false;
  const code = Math.trunc(value);
  if (code < 0) return false;
  if (node._set === undefined) {
    node._set = new Set(String(node.t).split('||').map(Number));   // memoised
  }
  return node._set.has(code);
}

function walk(node, row) {
  while (node.v === undefined) {
    node = goLeft(node, row[node.f]) ? node.L : node.R;
  }
  return node.v;
}

/** Sum every tree's leaf value for one feature row. */
export function predictTrees(trees, row) {
  let total = 0;
  for (let i = 0; i < trees.length; i++) total += walk(trees[i], row);
  return total;
}

/**
 * Turn a {featureName: value} object into the positional array the trees expect,
 * encoding categoricals to their integer codes.
 */
export function encodeRow(bundle, values) {
  const { features, categorical, categories } = bundle;
  const catSet = new Set(categorical);
  const row = new Array(features.length);
  for (let i = 0; i < features.length; i++) {
    const name = features[i];
    const raw = values[name];
    if (catSet.has(name)) {
      const idx = categories[name].indexOf(raw);
      row[i] = idx === -1 ? NaN : idx;      // unseen category behaves as missing
    } else if (raw === null || raw === undefined || raw === '') {
      row[i] = NaN;
    } else {
      row[i] = typeof raw === 'boolean' ? (raw ? 1 : 0) : Number(raw);
    }
  }
  return row;
}
