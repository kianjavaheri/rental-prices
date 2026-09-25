const usd = (n) => `$${Math.round(n).toLocaleString()}`;

const LABELS = {
  squareFootage: 'size', dist_coast_mi: 'distance to ocean', bedrooms: 'bedrooms',
  bathrooms: 'bathrooms', dist_ucsc_mi: 'distance to UCSC', dist_csumb_mi: 'distance to CSUMB',
  dist_hwy17_mi: 'distance to Hwy 17', dist_town_center_mi: 'distance to town centre',
  dist_sc_downtown_mi: 'distance to SC downtown', months_since_2020: 'listing date',
  listed_month: 'month of year', latitude: 'latitude', longitude: 'longitude',
  sqft_missing: 'size not stated', place: 'neighbourhood', propertyType: 'property type',
  place_kind: 'area type', county: 'county',
};

function Comparables({ comps }) {
  if (!comps.length) return null;
  return (
    <section>
      <h3>Nearby comparable listings</h3>
      <p className="muted">Actual rents from the data — the closest units with the same bedroom count.</p>
      <table className="comps">
        <tbody>
          {comps.map((c) => (
            <tr key={c.id}>
              <td className="addr">{c.addr}</td>
              <td className="num">{c.miles.toFixed(2)} mi</td>
              <td className="num">{c.sqft ? `${c.sqft.toLocaleString()} sqft` : '—'}</td>
              <td className="num strong">{usd(c.price)}</td>
              <td className="num muted">{c.date}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Why({ contributions }) {
  const top = contributions.slice(0, 7);
  if (!top.length) return null;
  const max = Math.max(...top.map((c) => Math.abs(c.pct)));
  return (
    <section>
      <h3>Why this number</h3>
      <p className="muted">
        How much the estimate moves when each input is swapped for a typical value.
      </p>
      <ul className="why">
        {top.map((c) => (
          <li key={c.name}>
            <span className="label">{LABELS[c.name] ?? c.name}</span>
            <span className="bar">
              <span
                className={c.pct >= 0 ? 'pos' : 'neg'}
                style={{ width: `${(Math.abs(c.pct) / max) * 100}%` }}
              />
            </span>
            <span className={`pct ${c.pct >= 0 ? 'pos' : 'neg'}`}>
              {c.pct >= 0 ? '+' : ''}{c.pct.toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ResultPanel({ result, block, comps, dateLabel }) {
  const unitLabel = result?.features.bedrooms === 0 ? 'studio' : '1-bedroom';
  if (!result) {
    return (
      <div className="panel empty" id="result">
        <h2>Pick a unit</h2>
        <p>
          Click any pin on the map, or search an address above. Blue pins are
          street blocks where studios and one-bedrooms have been listed; you can
          also price an address that isn&apos;t in the data.
        </p>
      </div>
    );
  }

  const years = block
    ? [...new Set(block.listings.map((l) => l.d.slice(0, 4)))].sort()
    : [];

  return (
    <div className="panel" id="result">
      <h2>{block ? block.addr : 'Entered unit'}</h2>
      <p className="muted sub">
        {result.derived.place} · {result.derived.county} County ·
        {' '}{result.derived.distCoast.toFixed(2)} mi from the ocean
      </p>

      <section className="estimate">
        <div className="mid">{usd(result.mid)}<span className="per">/mo</span></div>
        <div className="range">
          {usd(result.lo)} – {usd(result.hi)}
          <span className="muted"> · 80% range, as of {dateLabel}</span>
        </div>

        {/* The trend line supplies "typical for this date"; the model supplies
            this percentage. Time explains only ~7% of rent variation, so this
            is the part the model is actually doing. */}
        <div className="vs">
          <span className={`delta ${result.vsTypicalPct >= 0 ? 'pos' : 'neg'}`}>
            {result.vsTypicalPct >= 0 ? '+' : '−'}
            {Math.abs(result.vsTypicalPct).toFixed(0)}%
          </span>
          <span className="muted">
            vs a typical {unitLabel} in {dateLabel} ({usd(result.typical)})
          </span>
        </div>
      </section>

      {result.extrapolating && (
        <p className="warn">
          This date is past the end of the training data. The unit-level estimate
          still holds, but the overall market level is a straight-line assumption.
        </p>
      )}

      {block && (
        <section>
          <h3>What actually rented here</h3>
          {years.length === 1 ? (
            <p className="muted">
              This block appears in the data for <strong>{years[0]} only</strong>
              {block.listings.length > 1
                ? ` (${block.listings.length} listings that year).` : '.'}
            </p>
          ) : (
            <p className="muted">Listed in {years.join(', ')}.</p>
          )}
          {block.units > 1 && (
            <p className="muted small">
              {block.units} separate units on this block, grouped to ~100 m.
            </p>
          )}
          <table className="history">
            <tbody>
              {block.listings.map((l, i) => (
                <tr key={i}><td>{l.d}</td><td className="num strong">{usd(l.p)}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <Why contributions={result.contributions} />
      <Comparables comps={comps} />
    </div>
  );
}
