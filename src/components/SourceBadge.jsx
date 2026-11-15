import { Bluetooth, FlaskConical } from 'lucide-react';

// Origen de los datos de un trabajador: clip real por Bluetooth o simulación
export default function SourceBadge({ source, compact = false }) {
  if (source === 'clip') {
    return <span className="badge bg-emerald-50 text-emerald-700 border-emerald-300" title="Lecturas reales del clip por Bluetooth"><Bluetooth className="w-3 h-3" />{compact ? 'Real' : 'Clip real'}</span>;
  }
  return <span className="badge bg-slate-100 text-slate-500 border-slate-200" title="Telemetría generada por la simulación"><FlaskConical className="w-3 h-3" />{compact ? 'Sim.' : 'Simulado'}</span>;
}
