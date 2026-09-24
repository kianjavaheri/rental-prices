const TYPES = ['Apartment', 'Single Family', 'Condo', 'Townhouse', 'Multi-Family'];

export default function UnitForm({ input, onChange, disabled }) {
  const set = (k) => (e) => onChange({ ...input, [k]: e.target.value });
  return (
    <div className="unitform">
      <label>
        <span>Bedrooms</span>
        <select value={input.bedrooms} onChange={set('bedrooms')} disabled={disabled}>
          <option value={0}>Studio</option>
          <option value={1}>1 bedroom</option>
        </select>
      </label>
      <label>
        <span>Bathrooms</span>
        <input type="number" min="1" max="3" step="0.5"
               value={input.bathrooms ?? ''} onChange={set('bathrooms')} disabled={disabled} />
      </label>
      <label>
        <span>Square feet</span>
        <input type="number" min="150" max="1500" step="10" placeholder="unknown"
               value={input.squareFootage ?? ''} onChange={set('squareFootage')} disabled={disabled} />
      </label>
      <label>
        <span>Property type</span>
        <select value={input.propertyType} onChange={set('propertyType')} disabled={disabled}>
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>
    </div>
  );
}
