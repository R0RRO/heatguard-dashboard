import { Save, RotateCcw } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DEFAULT_THRESHOLDS } from '../lib/risk';

export default function Settings() {
  const { thresholds, setThresholds } = useApp();
  const set = (patch) => setThresholds((t) => {
    const next = { ...t, ...patch };
    if (next.attention >= next.alert) next.attention = next.alert - 5;
    return next;
  });

  return (
    <div className="page-layout max-w-3xl">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Umbrales de riesgo</h1>
        <p className="text-sm text-slate-500">Define cuándo el clip cambia de verde a azul (atención) y a rojo (riesgo alto). Se guardan en este navegador.</p>
      </div>

      <div className="card p-5 space-y-6">
        <div>
          <div className="flex justify-between text-sm"><label className="font-semibold text-ink">Umbral de atención (azul)</label><b className="text-blue-600">{thresholds.attention}</b></div>
          <input type="range" min="10" max="80" value={thresholds.attention} onChange={(e) => set({ attention: +e.target.value })} className="w-full accent-blue-600" />
        </div>
        <div>
          <div className="flex justify-between text-sm"><label className="font-semibold text-ink">Umbral de riesgo alto (rojo)</label><b className="text-red-600">{thresholds.alert}</b></div>
          <input type="range" min="30" max="95" value={thresholds.alert} onChange={(e) => set({ alert: +e.target.value })} className="w-full accent-red-600" />
        </div>
        <div className="h-3 rounded-full overflow-hidden flex">
          <div className="bg-green-500" style={{ width: `${thresholds.attention}%` }} />
          <div className="bg-blue-500" style={{ width: `${thresholds.alert - thresholds.attention}%` }} />
          <div className="bg-red-500 flex-1" />
        </div>
        <div>
          <div className="flex justify-between text-sm"><label className="font-semibold text-ink">Alerta por falta de movimiento</label><b className="text-ink-2">{thresholds.stillMinutes} min</b></div>
          <input type="range" min="3" max="20" value={thresholds.stillMinutes} onChange={(e) => set({ stillMinutes: +e.target.value })} className="w-full accent-orange-500" />
          <p className="text-xs text-slate-500 mt-1">Minutos sin movimiento (acelerómetro) en zona de trabajo antes de alertar. Las caídas alertan de inmediato.</p>
        </div>
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" className="mt-1 accent-orange-500" checked={thresholds.autoPause} onChange={(e) => set({ autoPause: e.target.checked })} />
          <span className="text-sm"><b className="text-ink">Pausa automática recomendada</b><br /><span className="text-slate-500">En la simulación, los trabajadores en riesgo alto tienden a tomar una pausa aunque nadie la ordene.</span></span>
        </label>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => setThresholds(DEFAULT_THRESHOLDS)}><RotateCcw className="w-4 h-4" />Restablecer</button>
          <span className="btn-navy cursor-default"><Save className="w-4 h-4" />Guardado automático</span>
        </div>
      </div>

      <div className="card p-5 text-sm text-slate-600 space-y-2">
        <h2 className="section-heading">¿Cómo se calcula el riesgo?</h2>
        <p>El puntaje (0–100) combina la <b>temperatura ambiente</b> (ajustada por humedad) 50%, la <b>exposición acumulada</b> 30% y la <b>actividad</b> 20% (acelerómetro). Además, el acelerómetro detecta caídas y falta de movimiento prolongada. Es un modelo de demostración: reemplázalo por el algoritmo real del clip en <code>src/lib/risk.js</code>.</p>
      </div>
    </div>
  );
}
