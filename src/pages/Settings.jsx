import { Save, RotateCcw } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DEFAULT_THRESHOLDS, STATUS } from '../lib/risk';

function Slider({ label, value, unit, min, max, step = 1, onChange, hint, accent = 'accent-orange-500', color }) {
  return (
    <div>
      <div className="flex justify-between text-sm">        <label className="font-semibold text-ink">{label}</label><b style={color ? { color } : undefined} className="text-ink-2">{value}{unit}</b></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} className={`w-full ${accent}`} />
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  );
}

export default function Settings() {
  const { thresholds: th, setThresholds } = useApp();
  const set = (patch) => setThresholds((t) => ({ ...t, ...patch }));

  return (
    <div className="page-layout max-w-3xl">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Pausas de hidratación y descanso</h1>
      </div>

      <div className="card p-5 space-y-6">
        <Slider label="Límite de exposición (100 %)" value={th.loadLimit} unit=" min-eq." min={30} max={240} step={10} onChange={(v) => set({ loadLimit: v })} />
        <Slider label="Cansancio (amarillo) desde" value={th.tiredPct} unit=" %" min={40} max={95} step={5} color={STATUS.cansancio.hex} accent="accent-yellow-500" onChange={(v) => set({ tiredPct: v })} />
        <div className="h-3 rounded-full overflow-hidden flex">
          <div style={{ width: `${th.tiredPct}%`, background: STATUS.normal.hex }} />
          <div style={{ width: `${100 - th.tiredPct}%`, background: STATUS.cansancio.hex }} />
          <div style={{ width: '8%', background: STATUS.descanso.hex }} />
        </div>
        <Slider label="Duración de la pausa" value={th.pauseMinutes} unit=" min" min={5} max={30} onChange={(v) => set({ pauseMinutes: v })} color={STATUS.pausa.hex} accent="accent-blue-600" />
        <Slider label="Alertar si no se comienza o no se cierra la pausa" value={th.confirmMinutes} unit=" min" min={2} max={15} onChange={(v) => set({ confirmMinutes: v })} />
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" className="mt-1 accent-orange-500" checked={th.autoPause} onChange={(e) => set({ autoPause: e.target.checked })} />
          <span className="text-sm"><b className="text-ink">Pedir la pausa al llegar al 100 %</b><br /><span className="text-slate-500">El clip pasa a rojo y vibra 5 veces cada 40 s. Si está apagado, solo el supervisor puede pedir pausas.</span></span>
        </label>
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" className="mt-1 accent-orange-500" checked={th.simResponds !== false} onChange={(e) => set({ simResponds: e.target.checked })} />
          <span className="text-sm"><b className="text-ink">Los trabajadores simulados presionan el botón</b><br /><span className="text-slate-500">En la simulación responden con el botón cuando el clip lo pide (comenzar o cerrar la pausa). Si está apagado, nada cambia hasta que uses «Simular botón» en el detalle de cada trabajador. No afecta al clip real.</span></span>
        </label>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => setThresholds(DEFAULT_THRESHOLDS)}><RotateCcw className="w-4 h-4" />Restablecer</button>
          <span className="btn-navy cursor-default"><Save className="w-4 h-4" />Guardado automático</span>
        </div>
      </div>

    </div>
  );
}
