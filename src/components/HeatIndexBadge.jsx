import { hiCategory } from '../lib/heatIndex';

// Categoría del Heat Index del NWS para un valor en °C
export default function HeatIndexBadge({ hi, showValue = false }) {
  const cat = hiCategory(hi);
  if (!cat) return <span className="badge bg-slate-100 text-slate-500 border-slate-200">Sin lectura</span>;
  return (
    <span className="badge" title={cat.text} style={{ color: cat.hex, borderColor: `${cat.hex}66`, background: `${cat.hex}14` }}>
      {showValue && <b>{hi.toFixed(1)} °C ·</b>}{cat.label}
    </span>
  );
}
