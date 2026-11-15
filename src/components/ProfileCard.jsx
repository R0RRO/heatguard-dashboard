import { useState } from 'react';
import { Ruler, Save } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { bmi, personalFactor } from '../lib/risk';

// Altura y peso del trabajador: definen el factor personal de la exposición acumulada
export default function ProfileCard({ w }) {
  const { setWorkerProfile } = useApp();
  const [h, setH] = useState(String(w.heightCm ?? ''));
  const [kg, setKg] = useState(String(w.weightKg ?? ''));
  const height = parseFloat(h);
  const weight = parseFloat(kg);
  const b = bmi(height, weight);
  const valid = b != null;
  const f = personalFactor(height, weight);
  const changed = height !== w.heightCm || weight !== w.weightKg;

  return (
    <div className="card p-4 space-y-3">
      <h2 className="section-heading"><Ruler className="w-4 h-4 text-ink-2" />Datos del trabajador</h2>
      <form className="flex items-end gap-3 flex-wrap" onSubmit={(e) => { e.preventDefault(); if (valid) setWorkerProfile(w.id, { heightCm: height, weightKg: weight }); }}>
        <label className="text-xs text-slate-500 flex flex-col">Altura (cm)
          <input className="form-input w-24 mt-1" type="number" min="120" max="230" step="1" value={h} onChange={(e) => setH(e.target.value)} />
        </label>
        <label className="text-xs text-slate-500 flex flex-col">Peso (kg)
          <input className="form-input w-24 mt-1" type="number" min="35" max="250" step="0.5" value={kg} onChange={(e) => setKg(e.target.value)} />
        </label>
        <button className="btn-primary btn-sm" disabled={!valid || !changed}><Save className="w-3.5 h-3.5" />Guardar</button>
      </form>
      <p className="text-sm text-ink">
        {valid ? <>IMC <b>{b.toFixed(1)}</b> · factor personal <b>×{f.toFixed(1)}</b></> : <span className="text-amber-700">Altura o peso fuera de rango: se usa factor ×1.</span>}
      </p>
    </div>
  );
}
