// Orchestrates a prediction: features -> trees -> trend -> dollars -> interval.

import { encodeRow, predictTrees } from './lgbm.js';
import { buildFeatures } from './features.js';

/** Log-space prediction, split into its two halves. */
function logParts(bundle, meta, features) {
  // trend  = what a typical studio/1BR costs on this date (the straight line)
  // resid  = what the trees say about THIS unit, relative to that typical value
  const trend = meta.trend.intercept + meta.trend.slope * features.months_since_2020;
  const resid = predictTrees(bundle.trees, encodeRow(bundle, features));
  return { trend, resid, total: trend + resid };
}

function logPrediction(bundle, meta, features) {
  return logParts(bundle, meta, features).total;
}

/**
 * @returns { mid, lo, hi, features, derived, contributions, extrapolating }
 */
export function predict(ctx, bundle, input) {
  const { meta } = ctx;
  const { features, derived } = buildFeatures(ctx, input);

  const { trend, resid, total: logMid } = logParts(bundle, meta, features);
  const k = meta.k;

  return {
    mid: Math.exp(logMid),
    lo: Math.exp(logMid - k),
    hi: Math.exp(logMid + k),
    // the model's actual contribution: how far this unit sits from a typical
    // one on the same date. The trend line supplies "typical"; the trees supply
    // this. Time explains only ~7% of rent variation -- this is the other 93%.
    typical: Math.exp(trend),
    vsTypicalPct: (Math.exp(resid) - 1) * 100,
    features,
    derived,
    contributions: contributions(bundle, meta, features, logMid),
    // trees cannot extrapolate; the trend line carries dates past training
    extrapolating: features.months_since_2020 > meta.trainRange.maxMonths,
  };
}

/**
 * "Why this number": for each feature, how much the prediction moves when that
 * feature is reset to its training median. Not SHAP -- a one-at-a-time swap,
 * which is cheap (24 x 600 tree walks) and honest about what it measures.
 */
function contributions(bundle, meta, features, logMid) {
  const out = [];
  for (const name of bundle.numeric) {
    const median = meta.medians[name];
    if (median == null || features[name] == null) continue;
    const swapped = { ...features, [name]: median };
    const delta = logMid - logPrediction(bundle, meta, swapped);
    if (Math.abs(delta) > 1e-6) {
      out.push({ name, delta, pct: (Math.exp(delta) - 1) * 100, value: features[name] });
    }
  }
  for (const name of bundle.categorical) {
    const modal = bundle.categories[name][0];
    if (features[name] === modal) continue;
    const swapped = { ...features, [name]: modal };
    const delta = logMid - logPrediction(bundle, meta, swapped);
    if (Math.abs(delta) > 1e-6) {
      out.push({ name, delta, pct: (Math.exp(delta) - 1) * 100,
                 value: features[name], vs: modal });
    }
  }
  return out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
}
