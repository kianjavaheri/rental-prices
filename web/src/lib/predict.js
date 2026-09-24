// Orchestrates a prediction: features -> trees -> trend -> dollars -> interval.

import { encodeRow, predictTrees } from './lgbm.js';
import { buildFeatures } from './features.js';

/** Log-space prediction for an already-built feature object. */
function logPrediction(bundle, meta, features) {
  const resid = predictTrees(bundle.trees, encodeRow(bundle, features));
  return meta.trend.intercept + meta.trend.slope * features.months_since_2020 + resid;
}

/**
 * @returns { mid, lo, hi, features, derived, contributions, extrapolating }
 */
export function predict(ctx, bundle, input) {
  const { meta } = ctx;
  const { features, derived } = buildFeatures(ctx, input);

  const logMid = logPrediction(bundle, meta, features);
  const k = meta.k;

  return {
    mid: Math.exp(logMid),
    lo: Math.exp(logMid - k),
    hi: Math.exp(logMid + k),
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
