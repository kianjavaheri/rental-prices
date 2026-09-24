// Address autocomplete. Known street blocks are matched locally; anything else
// goes to Photon (CORS-enabled, built for type-ahead, no API key).

const BBOX = '-122.40,36.35,-121.35,37.35';   // the study area

// Addresses in the data are abbreviated ("W Cliff Dr") but people type them out
// ("West Cliff Drive"). Normalise both sides to the same short form.
const SYNONYMS = {
  west: 'w', east: 'e', north: 'n', south: 's',
  northwest: 'nw', northeast: 'ne', southwest: 'sw', southeast: 'se',
  street: 'st', drive: 'dr', avenue: 'ave', av: 'ave', road: 'rd',
  boulevard: 'blvd', court: 'ct', lane: 'ln', place: 'pl', circle: 'cir',
  terrace: 'ter', highway: 'hwy', parkway: 'pkwy', apartment: 'apt',
  unit: '#', suite: '#', mount: 'mt', saint: 'st',
};

const UNIT_WORDS = /\b(apt|unit|ste|suite|no\.?)\b\s*[\w-]*|#\s*[\w-]*/gi;
const PURE_NUMBER = /^\d+(?:[/-]\d+)?[a-z]?$/i;

function normalise(text) {
  return text.toLowerCase()
    .replace(/[.,]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => SYNONYMS[w] ?? w)
    .join(' ');
}

/**
 * Drop the house number and unit designator, matching how blocks.json was
 * built. Applied to the SEARCH QUERY so that typing a full address
 * ("116 W Cliff Dr, Apt 1") still finds the "W Cliff Dr" block. Ordinal street
 * names ("17th Ave") are numbers but not house numbers, so they survive.
 */
export function stripAddressDetail(addr) {
  const [head, ...rest] = addr.split(',');
  const tokens = head.replace(UNIT_WORDS, ' ').split(/\s+/).filter(Boolean);
  while (tokens.length && PURE_NUMBER.test(tokens[0])) tokens.shift();
  const street = tokens.join(' ').trim();
  // Drop trailing "CA", "95060" and the combined "CA 95060" form
  const STATE_ZIP = /^(?:(?:ca|california)\s*)?\d{5}(?:-\d{4})?$|^(?:ca|california)$/i;
  const tail = rest
    .map((x) => x.replace(UNIT_WORDS, ' ').replace(/\s+/g, ' ').trim())
    .filter((x) => x && !STATE_ZIP.test(x));
  return [street, ...tail].filter(Boolean).join(', ');
}

/** Match dataset street blocks on a normalised address, best matches first. */
export function searchBlocks(blocks, query, limit = 6) {
  const q = normalise(stripAddressDetail(query));
  if (q.length < 2) return [];
  const out = [];
  for (const p of blocks) {
    if (p._norm === undefined) p._norm = normalise(p.addr);   // memoised
    const idx = p._norm.indexOf(q);
    if (idx === -1) continue;
    out.push({ ...p, _score: idx });
    if (out.length > 600) break;
  }
  return out
    .sort((a, b) => a._score - b._score || a.addr.length - b.addr.length)
    .slice(0, limit);
}

export async function geocode(query, signal) {
  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(query)}`
            + `&limit=5&bbox=${BBOX}`;
  const res = await fetch(url, { signal });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.features ?? []).map((f) => {
    const p = f.properties ?? {};
    const parts = [
      [p.housenumber, p.street].filter(Boolean).join(' ') || p.name,
      p.city || p.district, p.state,
    ].filter(Boolean);
    return {
      addr: parts.join(', '),
      lat: f.geometry.coordinates[1],
      lon: f.geometry.coordinates[0],
      external: true,
    };
  }).filter((r) => r.addr);
}
