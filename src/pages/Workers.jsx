import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Pause, Droplets } from 'lucide-react';
import { useApp } from '../context/AppContext';
import StatusBadge from '../components/StatusBadge';
import { RiskBar, Sparkline, BatteryPill } from '../components/Charts';
import { ZONES } from '../data/seed';
import { fmtDuration, distanceKm } from '../lib/format';
import { hydrationState, sinceDrink, HYDRATION_BADGE, HYDRATION_LABEL } from '../lib/hydration';

const FILTERS = [
  ['all', 'Todos'], ['alerta', 'Riesgo alto'], ['atencion', 'Atención'], ['normal', 'Normal'], ['pausa', 'En pausa'], ['incidente', 'Sin movimiento'], ['hidratacion', 'Hidratación pendiente'], ['offline', 'Sin señal'],
];

export default function Workers() {
  const { workers, workerStatus, orderPause, clock, thresholds } = useApp();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [zone, setZone] = useState('all');
  const [sort, setSort] = useState('risk');

  const list = useMemo(() => {
    let l = workers.filter((w) => {
      if (q && !`${w.name} ${w.trade} ${w.crew} ${w.deviceId}`.toLowerCase().includes(q.toLowerCase())) return false;
      if (zone !== 'all' && w.zoneId !== zone) return false;
      if (filter === 'incidente') { if (!w.incident) return false; }
      else if (filter === 'hidratacion') { if (hydrationState(w, clock, thresholds) === 'ok') return false; }
      else if (filter !== 'all' && workerStatus(w) !== filter) return false;
      return true;
    });
    const by = { risk: (a, b) => b.score - a.score, exposure: (a, b) => b.exposure - a.exposure, distance: (a, b) => distanceKm(b.history) - distanceKm(a.history), name: (a, b) => a.name.localeCompare(b.name) };
    return l.sort(by[sort]);
  }, [workers, q, filter, zone, sort, workerStatus, clock, thresholds]);

  return (
    <div className="page-layout">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Trabajadores</h1>
        <p className="text-sm text-slate-500">Lecturas en vivo de cada clip HeatGuard.</p>
      </div>

      <div className="card p-3 space-y-3">
        <div className="flex gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input className="form-input pl-9" placeholder="Buscar por nombre, oficio, cuadrilla o clip…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="form-select" value={zone} onChange={(e) => setZone(e.target.value)}>
            <option value="all">Todas las zonas</option>
            {ZONES.filter((z) => z.kind === 'trabajo').map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
          </select>
          <select className="form-select" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="risk">Ordenar: riesgo</option>
            <option value="exposure">Ordenar: exposición</option>
            <option value="distance">Ordenar: recorrido</option>
            <option value="name">Ordenar: nombre</option>
          </select>
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {FILTERS.map(([k, label]) => (
            <button key={k} onClick={() => setFilter(k)} className={filter === k ? 'btn-filter-active' : 'btn-filter'}>{label}</button>
          ))}
          <span className="ml-auto text-xs text-slate-500 self-center">{list.length} de {workers.length}</span>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line bg-surface-2/50">
            <tr>
              <th className="th">Trabajador</th><th className="th">Zona</th><th className="th">T° ambiente</th><th className="th">Humedad</th><th className="th">Actividad</th><th className="th">Recorrido 30 min</th>
              <th className="th">Exposición</th><th className="th">Hidratación</th><th className="th">Riesgo</th><th className="th">Tendencia riesgo</th><th className="th">Estado</th><th className="th">Clip</th><th className="th" />
            </tr>
          </thead>
          <tbody>
            {list.map((w) => {
              const st = workerStatus(w);
              return (
                <tr key={w.id} onClick={() => navigate(`/workers/${w.id}`)} className="border-b border-slate-50 hover:bg-heat-50/40 cursor-pointer">
                  <td className="td"><p className="font-semibold text-ink">{w.name}</p><p className="text-xs text-slate-500">{w.trade} · {w.crew}</p></td>
                  <td className="td text-slate-600">{ZONES.find((z) => z.id === w.zoneId).name}</td>
                  <td className="td">{w.env.t.toFixed(1)}°C</td>
                  <td className="td">{Math.round(w.env.rh)}%</td>
                  <td className="td">{Math.round(w.activity * 100)}%</td>
                  <td className="td">{distanceKm(w.history).toFixed(2)} km</td>
                  <td className="td">{fmtDuration(w.exposure)}</td>
                  <td className="td">{(() => { const hs = hydrationState(w, clock, thresholds); return (<div className="flex flex-col items-start gap-1"><span className="text-xs text-slate-600">hace {sinceDrink(w, clock)} min</span>{hs !== 'ok' && <span className={`badge ${HYDRATION_BADGE[hs]}`}><Droplets className="w-3 h-3" />{HYDRATION_LABEL[hs]}</span>}</div>); })()}</td>
                  <td className="td"><RiskBar score={w.score} status={w.status} /></td>
                  <td className="td"><Sparkline values={w.history.slice(-30).map((p) => p.score)} color="#f97316" /></td>
                  <td className="td"><div className="flex flex-col items-start gap-1"><StatusBadge status={st} pulse />{w.incident && <span className="badge bg-red-50 text-red-700 border-red-200">{w.incident.type === 'caida' ? 'Posible caída' : `Inmóvil ${w.stillMin} min`}</span>}</div></td>
                  <td className="td"><BatteryPill level={w.battery} /></td>
                  <td className="td">
                    {!w.resting && w.status !== 'normal' && (
                      <button className="btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); orderPause(w.id); }}><Pause className="w-3.5 h-3.5" />Pausa</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {list.length === 0 && <p className="text-center text-sm text-slate-500 py-10">Sin resultados con esos filtros.</p>}
      </div>
    </div>
  );
}
