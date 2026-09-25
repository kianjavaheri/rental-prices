import { useEffect, useMemo, useState } from 'react';
import { loadEverything } from './lib/data.js';
import { predict } from './lib/predict.js';
import { milesBetween, toAlbers } from './lib/geo.js';
import { stripAddressDetail } from './lib/geocode.js';
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
  const [block, setBlock] = useState(null);
  const [location, setLocation] = useState(null);
  const [monthIdx, setMonthIdx] = useState(TODAY_IDX);
  const [yearFilter, setYearFilter] = useState('all');
  const [showAbout, setShowAbout] = useState(false);
  const [input, setInput] = useState({
    bedrooms: 1, bathrooms: 1, squareFootage: '', propertyType: 'Apartment',
  });

  useEffect(() => { loadEverything().then(setData).catch((e) => setError(e.message)); }, []);

  function pick(item) {
    // Suggestions show the full address, but everything downstream works at
    // block resolution: coordinates rounded to ~100 m, house number dropped.
    // Keeps hand-entered addresses consistent with the published data.
    setLocation({
      lat: Math.round(item.lat * 1000) / 1000,
      lon: Math.round(item.lon * 1000) / 1000,
      addr: item.listings ? item.addr : stripAddressDetail(item.addr),
    });
    if (item.listings) {
      setBlock(item);
      setInput({
        bedrooms: item.beds,
        bathrooms: item.baths ?? 1,
        squareFootage: item.sqft ?? '',
        propertyType: item.type ?? 'Apartment',
      });
    } else {
      setBlock(null);                          // hand-entered address
    }
  }

  // Stacked layout puts the result below the map, off-screen. Picking a pin
  // would look like nothing happened, so bring the panel up to meet it.
  useEffect(() => {
    if (!location) return;
    if (!window.matchMedia('(max-width: 900px)').matches) return;
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.getElementById('result')
      ?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
  }, [location]);

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
    return data.blocks
      .filter((p) => p.beds === Number(input.bedrooms) && p.id !== block?.id)
      .map((p) => ({ ...p, miles: milesBetween(here, toAlbers(p.lon, p.lat)) }))
      .sort((a, b) => a.miles - b.miles)
      .slice(0, 6)
      .map((p) => {
        const last = p.listings.at(-1);
        return { ...p, price: last.p, date: last.d };
      });
  }, [data, location, input.bedrooms, block]);

  if (error) return <div className="loading">Could not load the model: {error}</div>;
  if (!data) return <div className="loading">Loading model…</div>;

  const dateLabel = `${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
  const years = ['all', 2020, 2021, 2022, 2023, 2024, 2025, 2026];

  return (
    <div className="app">
      <header>
        <div className="brand">
          <h1>Santa Cruz Rent Model</h1>
          <span className="muted">
            studios &amp; 1-bedrooms · {data.meta.counts.blocks.toLocaleString()} blocks
            {' · '}{data.meta.counts.units.toLocaleString()} units
          </span>
        </div>
        <SearchBox blocks={data.blocks} onPick={pick} />
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
        <MapView blocks={data.blocks} selected={location && { ...location, id: block?.id }}
                 onSelect={pick} year={yearFilter} />
        <ResultPanel result={result} block={block} comps={comps} dateLabel={dateLabel} />
      </main>

      {showAbout && <About meta={data.meta} onClose={() => setShowAbout(false)} />}
    </div>
  );
}
