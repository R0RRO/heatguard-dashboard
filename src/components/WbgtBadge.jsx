import { WBGT_LEVELS } from '../lib/risk';

// Nivel del WBGT estimado (motor Python: modelo de Ono con meteorología regional)
export default function WbgtBadge({ wbgt, showValue = false }) {
  if (!wbgt) return null;
  const lv = WBGT_LEVELS[Math.max(0, Math.min(4, wbgt.level))];
  return (
    <span className="badge" title="WBGT estimado por modelo (Ono) con radiación y viento de Open-Meteo; no es WBGT medido ni ISO 7243"
      style={{ color: lv.hex, borderColor: `${lv.hex}66`, background: `${lv.hex}14` }}>
      {showValue && <b>{wbgt.c.toFixed(1)} °C ·</b>}{lv.label}
    </span>
  );
}
