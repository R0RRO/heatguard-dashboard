import { Play, Pause, RotateCcw, Sun } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { fmtClock } from '../lib/format';

export default function SimControls() {
  const { running, setRunning, speed, setSpeed, heatOffset, setHeatOffset, clock, resetSim } = useApp();
  return (
    <div className="card px-3 py-2 flex items-center gap-3 flex-wrap text-xs">
      <span className="badge bg-surface-2 text-ink-2 border-line-2">Simulación</span>
      <span className="font-mono font-semibold text-ink text-sm">{fmtClock(clock)}</span>
      <button onClick={() => setRunning(!running)} className="btn-secondary btn-sm" title={running ? 'Pausar' : 'Reanudar'}>
        {running ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
      </button>
      <div className="flex gap-1">
        {[1, 3, 6].map((s) => (
          <button key={s} onClick={() => setSpeed(s)} className={speed === s ? 'btn-filter-active' : 'btn-filter'}>{s}x</button>
        ))}
      </div>
      <label className="flex items-center gap-1.5 text-slate-600">
        <Sun className="w-3.5 h-3.5 text-heat-500" /> Ola de calor
        <input type="range" min="-4" max="8" step="1" value={heatOffset} onChange={(e) => setHeatOffset(+e.target.value)} className="accent-orange-500 w-24" />
        <b className="w-8 text-ink">{heatOffset > 0 ? '+' : ''}{heatOffset}°</b>
      </label>
      <button onClick={resetSim} className="btn-secondary btn-sm" title="Reiniciar simulación"><RotateCcw className="w-3.5 h-3.5" /></button>
    </div>
  );
}
