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
import { useStableOrder } from '../hooks/useStableOrder';

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
  // los valores se actualizan en vivo, pero el orden de las filas solo cada 10 s (o al cambiar filtros)
  const shown = useStableOrder(list, [q, filter, zone, sort, liveIds.join()].join('|'));

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
          <label className="flex items-center gap-2 text-sm text-slate-500 whitespace-nowrap">
            Ordenar por
            <select className="form-select" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="load">Exposición</option>
              <option value="hi">Sensación térmica (Heat Index)</option>
              <option value="name">Nombre</option>
            </select>
          </label>
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
              <th className="th-c">Trabajador</th><th className="th-c">Ambiente · sensación térmica (HI)</th><th className="th-c">Movimiento</th>
              <th className="th-c">Exposición acumulada</th><th className="th-c">Estado</th><th className="th-c">Clip</th><th className="th-c" />
            </tr>
          </thead>
          <tbody>
            {shown.map((w) => {
              const st = workerStatus(w);
              const zone = ZONES.find((z) => z.id === w.zoneId).name;
              return (
                <tr key={w.id} onClick={() => navigate(`/workers/${w.id}`)} className={liveIds.includes(w.id) ? 'live-row cursor-pointer' : 'border-b border-slate-50 hover:bg-heat-50/40 cursor-pointer'}>
                  <td className="td-c">
                    <p className="font-semibold text-ink">{w.name}</p>
                    <p className="text-xs text-slate-500">{w.trade} · {w.crew}</p>
                    <p className="text-xs text-slate-400">{zone}</p>
                    {liveIds.includes(w.id) && <SourceBadge source="clip" />}
                  </td>
                  <td className="td-c">
                    <p>{w.env.t.toFixed(1)} °C · {Math.round(w.env.rh)} %</p>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap"><span className="text-xs text-slate-600">{w.env.hi.toFixed(1)} °C</span><HeatIndexBadge hi={w.env.hi} /></div>
                  </td>
                  <td className="td-c whitespace-nowrap">{movDetail(w.activity * 100)}</td>
                  <td className="td-c">
                    <LoadBar load={w.load} status={st} />
                    <div className="mt-1"><Sparkline values={w.history.slice(-30).map((p) => p.load)} color="#f97316" width={110} height={18} /></div>
                  </td>
                  <td className="td-c">
                    <div className="flex flex-col items-start gap-1">
                      {(w.resting || w.pauseReq) && st !== 'offline' ? <PauseBadge w={w} clock={clock} /> : <StatusBadge status={st} pulse />}
                      <span className="text-xs text-slate-500">{w.pausesToday} {w.pausesToday === 1 ? 'pausa' : 'pausas'} hoy{!w.resting && w.pausesToday > 0 ? ` · última hace ${Math.max(0, clock - w.lastPauseEnd)} min` : ''}</span>
                    </div>
                  </td>
                  <td className="td-c"><BatteryPill level={w.battery} /></td>
                  <td className="td-c">
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
