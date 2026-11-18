import { useState } from 'react';
import { Play, Pause, RotateCcw, Sun } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { fmtClock } from '../lib/format';
import { SPEED_MIN, SPEED_MAX } from '../lib/simulation';

const PRESETS = [1, 3, 6];
const fmtSpeed = (v) => (v === SPEED_MIN ? 'tiempo real' : `×${String(+v.toFixed(3)).replace('.', ',')}`);

// Velocidad del reloj simulado: ×1 = 1 minuto simulado cada 1,5 s; ×0,025 ≈ tiempo real
function SpeedControl({ speed, setSpeed }) {
  const [draft, setDraft] = useState(null);
  const apply = () => {
    const v = parseFloat(String(draft).replace(',', '.'));
    if (Number.isFinite(v)) setSpeed(Math.min(SPEED_MAX, Math.max(SPEED_MIN, v)));
    setDraft(null);
  };
  return (
    <div className="flex items-center gap-1">
      <button onClick={() => setSpeed(SPEED_MIN)} className={speed === SPEED_MIN ? 'btn-filter-active' : 'btn-filter'}>Tiempo real</button>
      {PRESETS.map((s) => (
        <button key={s} onClick={() => setSpeed(s)} className={speed === s ? 'btn-filter-active' : 'btn-filter'}>{fmtSpeed(s)}</button>
      ))}
      <label className="flex items-center gap-1 ml-1 text-slate-600">×
        <input className="form-input w-16 py-1 text-xs" inputMode="decimal" aria-label="Velocidad de la simulación"
          value={draft ?? String(speed).replace('.', ',')}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={apply}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setDraft(null); }} />
      </label>
    </div>
  );
}

export default function SimControls() {
  const { running, setRunning, speed, setSpeed, heatOffset, setHeatOffset, clock, resetSim, liveIds, wbgtStatus } = useApp();
  const wbgtInfo = {
    ok: ['WBGT estimado activo', 'bg-emerald-50 text-emerald-700 border-emerald-300'],
    sin_meteorologia: ['WBGT sin meteorología · se usa sensación térmica', 'bg-amber-50 text-amber-700 border-amber-300'],
    caido: ['Motor WBGT no disponible · se usa sensación térmica', 'bg-amber-50 text-amber-700 border-amber-300'],
  }[wbgtStatus];
  return (
    <div className="card px-3 py-2 flex items-center gap-3 flex-wrap text-xs">
      <span className="badge bg-surface-2 text-ink-2 border-line-2">Simulación</span>
      {liveIds.length > 0 && <span className="badge bg-emerald-50 text-emerald-700 border-emerald-300">+ {liveIds.length} clip{liveIds.length > 1 ? 's' : ''} real{liveIds.length > 1 ? 'es' : ''}</span>}
      {wbgtInfo && <span className={`badge ${wbgtInfo[1]}`}>{wbgtInfo[0]}</span>}
      <span className="font-mono font-semibold text-ink text-sm">{fmtClock(clock)}</span>
      <button onClick={() => setRunning(!running)} className="btn-secondary btn-sm" title={running ? 'Pausar' : 'Reanudar'}>
        {running ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
      </button>
      <SpeedControl speed={speed} setSpeed={setSpeed} />
      <>
          <label className="flex items-center gap-1.5 text-slate-600">
            <Sun className="w-3.5 h-3.5 text-heat-500" /> Ola de calor
            <input type="range" min="-4" max="8" step="1" value={heatOffset} onChange={(e) => setHeatOffset(+e.target.value)} className="accent-orange-500 w-24" />
            <b className="w-8 text-ink">{heatOffset > 0 ? '+' : ''}{heatOffset}°</b>
          </label>
          <button onClick={resetSim} className="btn-secondary btn-sm" title="Reiniciar simulación"><RotateCcw className="w-3.5 h-3.5" /></button>
      </>
    </div>
  );
}
