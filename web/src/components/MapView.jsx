import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { useEffect, useMemo } from 'react';

const CENTER = [36.87, -121.90];

function Recenter({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lon], Math.max(map.getZoom(), 15), { duration: 0.6 });
  }, [target, map]);
  return null;
}

export default function MapView({ properties, selected, onSelect, year }) {
  // A property shows on the map if it has a listing in ANY year. When a year is
  // chosen we dim the ones that have no listing in that year rather than hiding
  // them, so the map does not appear to lose half its pins.
  const markers = useMemo(() => properties.map((p) => ({
    ...p,
    inYear: year === 'all' || p.listings.some((l) => l.d.startsWith(String(year))),
  })), [properties, year]);

  return (
    <MapContainer center={CENTER} zoom={10} className="map" preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Recenter target={selected} />
      <MarkerClusterGroup chunkedLoading maxClusterRadius={45} disableClusteringAtZoom={16}>
        {markers.map((p) => (
          <CircleMarker
            key={p.id}
            center={[p.lat, p.lon]}
            radius={selected?.id === p.id ? 9 : 5}
            pathOptions={{
              color: selected?.id === p.id ? '#b45309' : (p.inYear ? '#2563eb' : '#94a3b8'),
              fillColor: selected?.id === p.id ? '#f59e0b' : (p.inYear ? '#3b82f6' : '#cbd5e1'),
              fillOpacity: p.inYear ? 0.85 : 0.35,
              weight: selected?.id === p.id ? 3 : 1,
            }}
            eventHandlers={{ click: () => onSelect(p) }}
          >
            <Tooltip>
              <strong>{p.addr}</strong><br />
              {p.beds === 0 ? 'studio' : '1 bedroom'}
              {p.sqft ? ` · ${p.sqft.toLocaleString()} sqft` : ''}<br />
              {p.listings.length} listing{p.listings.length > 1 ? 's' : ''}
              {' '}({p.listings[0].d.slice(0, 4)}
              {p.listings.length > 1 ? `–${p.listings.at(-1).d.slice(0, 4)}` : ''})
            </Tooltip>
          </CircleMarker>
        ))}
      </MarkerClusterGroup>
    </MapContainer>
  );
}
