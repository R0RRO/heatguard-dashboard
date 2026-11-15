import { Pause, Hourglass, BellRing } from 'lucide-react';
import { useApp } from '../context/AppContext';

// Estado de la pausa de hidratación y descanso: solicitada, en curso o cumplida (sin cerrar)
export default function PauseBadge({ w, clock }) {
  const { thresholds } = useApp();
  if (w.resting) {
    const min = Math.max(0, Math.round(clock - w.pauseStart));
    const done = min >= thresholds.pauseMinutes;
    const Icon = done ? BellRing : Pause;
    return (
      <span className={`badge ${done ? 'bg-indigo-50 text-indigo-700 border-indigo-300' : 'bg-blue-50 text-blue-700 border-blue-200'}`}>
        <Icon className="w-3 h-3" />{done ? 'Pausa cumplida' : 'En pausa'} · hace {min} min
      </span>
    );
  }
  if (w.pauseReq) {
    const min = Math.max(0, Math.round(clock - w.pauseReq.since));
    return (
      <span className="badge bg-red-50 text-red-700 border-red-200">
        <Hourglass className="w-3 h-3" />Toca descanso ({w.pauseReq.source === 'supervisor' ? 'supervisor' : 'clip'}) · hace {min} min
      </span>
    );
  }
  return null;
}
