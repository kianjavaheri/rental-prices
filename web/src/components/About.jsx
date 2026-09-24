export default function About({ meta, onClose }) {
  const m = meta.metrics;
  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-body" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <h2>About this model</h2>

        <p>
          A gradient-boosted tree model predicting asking rent for studios and
          one-bedrooms in Santa Cruz and Monterey counties, trained on{' '}
          {m.n_train.toLocaleString()} listings from 2020–2025 and tested on{' '}
          {m.n_test.toLocaleString()} from 2026. It runs entirely in your browser.
        </p>

        <table className="metrics">
          <tbody>
            <tr><td>Typical error</td><td>{m.mape}% (about ${m.mae} on a $2,400 unit)</td></tr>
            <tr><td>Range accuracy</td><td>{Math.round(m.coverage * 100)}% of actual rents fall inside the shown range</td></tr>
            <tr><td>Beats a lookup table by</td><td>15.2% → {m.mape}% error</td></tr>
          </tbody>
        </table>

        <h3>What it cannot see</h3>
        <ul>
          <li>
            <strong>No amenities.</strong> The data source provides no listing
            description, so views, renovations, furnishing, utilities, parking and
            laundry are all invisible. Two units identical on every field here
            ranged from $1,600 to $6,500 in Pacific Grove.
          </li>
          <li>
            <strong>Extremes get pulled to the middle.</strong> Expensive units are
            under-predicted (by ~$500 in the top fifth) and cheap ones
            over-predicted. Trust it most between $1,850 and $2,700.
          </li>
          <li>
            <strong>Accuracy varies by area</strong> — about 9% error in Monterey and
            Salinas, 17% in unincorporated areas where there is less data.
          </li>
          <li>
            <strong>ADUs and cottages are under-represented.</strong> The feed draws on
            MLS and syndicated listings, which miss much of the informal
            studio/1BR market here.
          </li>
          <li>
            <strong>Asking rent, not contract rent.</strong> Long-tenured
            below-market tenancies never appear.
          </li>
          <li>
            <strong>Some coordinates are wrong.</strong> The source geocoder
            misplaces a small number of addresses &mdash; 116 and 200 West Cliff
            Drive sit about half a mile inland in the data, when both are on the
            water. Where a pin looks misplaced, the distance-to-ocean input is
            wrong too, and the estimate with it.
          </li>
          <li>
            <strong>It does not forecast the market.</strong> It prices a unit
            against the prevailing market; where that market sits on a future date
            comes from a fitted trend line, not from evidence.
          </li>
        </ul>

        <h3>Deployed model vs. full model</h3>
        <p className="muted">
          The browser runs an 18-feature model ({m.mape}% error) rather than the
          24-feature one from the analysis ({m.fullModel.mape}%). The five omitted
          features are census-tract and ZIP-level market averages that would need
          about 2 MB of extra polygon data to compute exactly in-browser, and are
          worth 0.3 percentage points. Every remaining feature is computed here
          exactly as it was during training — verified against the Python model on
          300 listings, to the last decimal place.
        </p>
      </div>
    </div>
  );
}
