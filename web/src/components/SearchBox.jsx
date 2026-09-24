import { useEffect, useRef, useState } from 'react';
import { geocode, searchBlocks, stripAddressDetail } from '../lib/geocode.js';

export default function SearchBox({ blocks, onPick }) {
  const [q, setQ] = useState('');
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef(null);

  useEffect(() => {
    if (q.trim().length < 2) { setItems([]); return; }
    const local = searchBlocks(blocks, q);
    setItems(local);                                   // instant, from the dataset
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const remote = await geocode(q, ctrl.signal);
        const seen = new Set(local.map((r) => r.addr.toLowerCase()));
        setItems([...local, ...remote.filter((r) => !seen.has(r.addr.toLowerCase()))]);
      } catch { /* aborted or offline — local results stand */ }
    }, 250);                                           // debounce the network call
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [q, blocks]);

  useEffect(() => {
    const away = (e) => { if (!box.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, []);

  function choose(item) {
    onPick(item);
    setQ(item.listings ? item.addr : stripAddressDetail(item.addr));
    setOpen(false);
  }

  function onKeyDown(e) {
    if (!open || !items.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % items.length); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + items.length) % items.length); }
    if (e.key === 'Enter') { e.preventDefault(); choose(items[active]); }
    if (e.key === 'Escape') setOpen(false);
  }

  return (
    <div className="search" ref={box}>
      <input
        value={q}
        placeholder="Search an address, or click a pin on the map"
        onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && items.length > 0 && (
        <ul className="suggestions">
          {items.map((it, i) => (
            <li
              key={`${it.addr}-${i}`}
              className={i === active ? 'active' : ''}
              onMouseEnter={() => setActive(i)}
              onMouseDown={() => choose(it)}
            >
              <span className="addr">
                {it.addr}
                {!it.external && (
                  <em className="beds">{it.beds === 0 ? 'studio' : '1br'}</em>
                )}
              </span>
              <span className={`tag ${it.external ? 'ext' : 'known'}`}>
                {it.external
                  ? 'address'
                  : `${it.listings.length} listing${it.listings.length > 1 ? 's' : ''}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
