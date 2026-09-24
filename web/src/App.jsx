import { useEffect, useMemo, useState } from 'react';
import { loadEverything } from './lib/data.js';
import { predict } from './lib/predict.js';
import { milesBetween, toAlbers } from './lib/geo.js';
import MapView from './components/MapView.jsx';
import SearchBox from './components/SearchBox.jsx';
import ResultPanel from './components/ResultPanel.jsx';
import UnitForm from './components/UnitForm.jsx';
import About from './components/About.jsx';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// slider runs over months from 2020-01 to two years past today
const START = new Date(Date.UTC(2020, 0, 1));
const monthsBetween = (a, b) =>
  (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth());
const TODAY_IDX = monthsBetween(START, new Date());
const MAX_IDX = TODAY_IDX + 24;
const idxToDate = (i) => new Date(Date.UTC(2020 + Math.floor(i / 12), i % 12, 1));

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [property, setProperty] = useState(null);
  const [location, setLocation] = useState(null);
  const [monthIdx, setMonthIdx] = useState(TODAY_IDX);
  const [yearFilter, setYearFilter] = useState('all');
  const [showAbout, setShowAbout] = useState(false);
  const [input, setInput] = useState({
    bedrooms: 1, bathrooms: 1, squareFootage: '', propertyType: 'Apartment',
  });

  useEffect(() => { loadEverything().then(setData).catch((e) => setError(e.message)); }, []);

  function pick(item) {
    setLocation({ lat: item.lat, lon: item.lon, addr: item.addr });
    if (item.listings) {
      setProperty(item);
      setInput({
        bedrooms: item.beds,
        bathrooms: item.baths ?? 1,
        squareFootage: item.sqft ?? '',
        propertyType: item.type ?? 'Apartment',
      });
    } else {
      setProperty(null);                       // hand-entered address
    }
  }

  const date = useMemo(() => idxToDate(monthIdx), [monthIdx]);

  const result = useMemo(() => {
    if (!data || !location) return null;
    return predict(data.ctx, data.bundle, {
      lat: location.lat, lon: location.lon, date,
      bedrooms: Number(input.bedrooms),
      bathrooms: input.bathrooms === '' ? null : Number(input.bathrooms),
      squareFootage: input.squareFootage === '' ? null : Number(input.squareFootage),
      propertyType: input.propertyType,
    });
  }, [data, location, input, date]);

  const comps = useMemo(() => {
    if (!data || !location) return [];
    const here = toAlbers(location.lon, location.lat);
    return data.properties
      .filter((p) => p.beds === Number(input.bedrooms) && p.id !== property?.id)
      .map((p) => ({ ...p, miles: milesBetween(here, toAlbers(p.lon, p.lat)) }))
      .sort((a, b) => a.miles - b.miles)
      .slice(0, 6)
      .map((p) => {
        const last = p.listings.at(-1);
        return { ...p, price: last.p, date: last.d };
      });
  }, [data, location, input.bedrooms, property]);

  if (error) return <div className="loading">Could not load the model: {error}</div>;
  if (!data) return <div className="loading">Loading model…</div>;

  const dateLabel = `${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
  const years = ['all', 2020, 2021, 2022, 2023, 2024, 2025, 2026];

  return (
    <div className="app">
      <header>
        <div className="brand">
          <h1>Santa Cruz Rent Model</h1>
          <span className="muted">studios &amp; 1-bedrooms · {data.properties.length.toLocaleString()} units</span>
        </div>
        <SearchBox properties={data.properties} onPick={pick} />
        <button className="about-btn" onClick={() => setShowAbout(true)}>
          How good is this?
        </button>
      </header>

      <div className="controls">
        <label className="slider">
          <span>Pricing as of <strong>{dateLabel}</strong></span>
          <input type="range" min={0} max={MAX_IDX} value={monthIdx}
                 onChange={(e) => setMonthIdx(Number(e.target.value))} />
          <span className="ends"><em>2020</em><em>{idxToDate(MAX_IDX).getUTCFullYear()}</em></span>
        </label>
        <label className="yearfilter">
          <span>Highlight units listed in</span>
          <select value={yearFilter} onChange={(e) => setYearFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}>
            {years.map((y) => <option key={y} value={y}>{y === 'all' ? 'any year' : y}</option>)}
          </select>
        </label>
        <UnitForm input={input} onChange={setInput} disabled={!location} />
      </div>

      <main>
        <MapView properties={data.properties} selected={location && { ...location, id: property?.id }}
                 onSelect={pick} year={yearFilter} />
        <ResultPanel result={result} property={property} comps={comps} dateLabel={dateLabel} />
      </main>

      {showAbout && <About meta={data.meta} onClose={() => setShowAbout(false)} />}
    </div>
  );
}
