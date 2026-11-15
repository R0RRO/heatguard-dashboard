import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Pause } from 'lucide-react';
import { useApp } from '../context/AppContext';
import StatusBadge from '../components/StatusBadge';
import { LoadBar, Sparkline, BatteryPill } from '../components/Charts';
import { ZONES } from '../data/seed';
import HeatIndexBadge from '../components/HeatIndexBadge';
import SourceBadge from '../components/SourceBadge';
import PauseBadge from '../components/PauseBadge';
import { movDetail } from '../lib/format';

const FILTERS = [
  ['all', 'Todos'], ['descanso', 'Toca descanso'], ['cansancio', 'Cansancio'], ['normal', 'Óptimo'], ['pausa', 'En pausa'], ['offline', 'Sin señal'],
];

export default function Workers() {
  const { workers, workerStatus, orderPause, clock, thresholds, liveIds } = useApp();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [zone, setZone] = useState('all');
  const [sort, setSort] = useState('load');

  const list = useMemo(() => {
    let l = workers.filter((w) => {
      if (q && !`${w.name} ${w.trade} ${w.crew} ${w.deviceId}`.toLowerCase().includes(q.toLowerCase())) return false;
      if (zone !== 'all' && w.zoneId !== zone) return false;
      if (filter === 'pausa') { if (!w.resting) return false; }
      else if (filter !== 'all' && workerStatus(w) !== filter) return false;
      return true;
    });
    const by = { load: (a, b) => b.load - a.load, hi: (a, b) => b.env.hi - a.env.hi, name: (a, b) => a.name.localeCompare(b.name) };
    l = l.sort(by[sort]);
    // El trabajador con el clip real va siempre primero, aunque no calce con los filtros
    const pinned = workers.filter((w) => liveIds.includes(w.id));
    return [...pinned, ...l.filter((w) => !liveIds.includes(w.id))];
  }, [workers, q, filter, zone, sort, workerStatus, liveIds]);

  return (
    <div className="page-layout">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Trabajadores</h1>
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
            <option value="load">Ordenar: exposición</option>
            <option value="hi">Ordenar: sensación térmica (Heat Index)</option>
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
              <th className="th">Trabajador</th><th className="th">Zona</th><th className="th">T° del aire</th><th className="th">Humedad</th><th className="th">Sensación térmica (Heat Index)</th><th className="th">Movimiento</th>
              <th className="th">Exposición acumulada</th><th className="th">Tendencia</th><th className="th">Pausas</th><th className="th">Estado</th><th className="th">Clip</th><th className="th" />
            </tr>
          </thead>
          <tbody>
            {list.map((w) => {
              const st = workerStatus(w);
              return (
                <tr key={w.id} onClick={() => navigate(`/workers/${w.id}`)} className={liveIds.includes(w.id) ? 'live-row cursor-pointer' : 'border-b border-slate-50 hover:bg-heat-50/40 cursor-pointer'}>
                  <td className="td"><p className="font-semibold text-ink">{w.name}</p><p className="text-xs text-slate-500">{w.trade} · {w.crew}</p>{liveIds.includes(w.id) && <SourceBadge source="clip" />}</td>
                  <td className="td text-slate-600">{ZONES.find((z) => z.id === w.zoneId).name}</td>
                  <td className="td">{w.env.t.toFixed(1)}°C</td>
                  <td className="td">{Math.round(w.env.rh)}%</td>
                  <td className="td"><div className="flex flex-col items-start gap-1"><span>{w.env.hi.toFixed(1)}°C</span><HeatIndexBadge hi={w.env.hi} /></div></td>
                  <td className="td">{movDetail(w.activity * 100)}</td>
                  <td className="td"><LoadBar load={w.load} status={st} /></td>
                  <td className="td"><Sparkline values={w.history.slice(-30).map((p) => p.load)} color="#f97316" /></td>
                  <td className="td"><div className="flex flex-col items-start gap-1"><span className="text-xs text-slate-600">{w.pausesToday} hoy</span>{!w.resting && <span className="text-xs text-slate-400">última hace {Math.max(0, clock - w.lastPauseEnd)} min</span>}</div></td>
                  <td className="td"><div className="flex flex-col items-start gap-1"><StatusBadge status={st} pulse /><PauseBadge w={w} clock={clock} /></div></td>
                  <td className="td"><BatteryPill level={w.battery} /></td>
                  <td className="td">
                    {!w.resting && !w.pauseReq && w.status === 'cansancio' && (
                      <button className="btn-primary btn-sm" title="Solicitar pausa al clip" onClick={(e) => { e.stopPropagation(); orderPause(w.id, thresholds.pauseMinutes); }}><Pause className="w-3.5 h-3.5" />Pausa</button>
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
