import { Link } from 'react-router-dom';
import { Users, ShieldAlert, Activity, Thermometer, Timer, Siren, Pause, Droplets, ArrowRight, Wifi, MousePointerClick, BellRing } from 'lucide-react';
import { useApp } from '../context/AppContext';
import KpiCard from '../components/KpiCard';
import SimControls from '../components/SimControls';
import AlertItem from '../components/AlertItem';
import StatusBadge from '../components/StatusBadge';
import { LineChart, StackedArea, Donut, RiskBar } from '../components/Charts';
import { ZONES, SITE } from '../data/seed';
import { STATUS, STATUS_RANK } from '../lib/risk';
import { fmtClock, fmtDuration } from '../lib/format';
import { hydrationState, sinceDrink } from '../lib/hydration';

export default function Dashboard() {
  const { workers, alerts, siteHistory, clock, thresholds, orderPause, hydrate, events, workerStatus } = useApp();

  const count = { normal: 0, atencion: 0, alerta: 0 };
  workers.forEach((w) => count[w.status]++);
  const online = workers.filter((w) => w.online).length;
  const resting = workers.filter((w) => w.resting).length;
  const incidents = workers.filter((w) => w.incident);
  const last = siteHistory[siteHistory.length - 1];
  const avgExposure = workers.reduce((a, w) => a + w.exposure, 0) / workers.length;

  const hyd = workers.map((w) => ({ w, st: hydrationState(w, clock, thresholds), since: sinceDrink(w, clock) }));
  const hydOk = hyd.filter((h) => h.st === 'ok').length;
  const hydPending = hyd.filter((h) => h.st !== 'ok').sort((a, b) => b.since - a.since);
  const hydEvents = events.filter((e) => e.type === 'hidratacion').slice(0, 6);

  const top = [...workers].filter((w) => w.status !== 'normal' && !w.resting).sort((a, b) => b.score - a.score).slice(0, 6);
  const openAlerts = alerts.filter((a) => a.status !== 'resuelta').slice(0, 5);

  return (
    <div className="page-layout">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-extrabold text-ink">Panel de obra</h1>
          <p className="text-sm text-slate-500">{SITE.name} · {SITE.company} · turno {fmtClock(clock)}</p>
        </div>
        <SimControls />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
        <KpiCard icon={Users} label="Trabajadores en obra" value={workers.length} hint={`${online} clips en línea · ${resting} en pausa`} />
        <KpiCard icon={ShieldAlert} label="Riesgo alto" value={count.alerta} tone="red" hint={`umbral ≥ ${thresholds.alert}`} />
        <KpiCard icon={Activity} label="En atención" value={count.atencion} tone="blue" hint={`umbral ≥ ${thresholds.attention}`} />
        <KpiCard icon={Thermometer} label="Temp. ambiente" value={last.temp.toFixed(1)} unit="°C" tone="heat" hint={`humedad ${Math.round(last.rh)}%`} />
        <KpiCard icon={Timer} label="Exposición promedio" value={fmtDuration(avgExposure)} tone="green" hint="acumulada en el turno" />
        <KpiCard icon={Droplets} label="Hidratación al día" value={Math.round((hydOk / workers.length) * 100)} unit="%" tone={hydPending.length > workers.length / 3 ? 'heat' : 'blue'} hint={`${hydPending.length} con recordatorio · botón del clip`} />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card p-4 lg:col-span-2 space-y-4">
          <div>
            <h2 className="section-heading mb-2">Evolución del estado de la cuadrilla</h2>
            <StackedArea data={siteHistory} series={[
              { key: 'normal', label: 'Normal', color: STATUS.normal.hex },
              { key: 'atencion', label: 'Atención', color: STATUS.atencion.hex },
              { key: 'alerta', label: 'Riesgo alto', color: STATUS.alerta.hex },
            ]} />
          </div>
          <div>
            <h2 className="section-heading mb-2">Temperatura ambiente de la obra</h2>
            <LineChart data={siteHistory} yDomain={[15, 50]}
              lines={[{ key: 'temp', label: 'Temp. ambiente', color: '#f97316', unit: '°C' }]}
              refLines={[{ value: 35, color: '#dc2626', label: '35°C alto riesgo' }]} />
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-4">
            <h2 className="section-heading mb-3">Estado actual</h2>
            <Donut center={{ value: workers.length, label: 'trabajadores' }} segments={[
              { label: 'Normal', value: count.normal, color: STATUS.normal.hex },
              { label: 'Atención', value: count.atencion, color: STATUS.atencion.hex },
              { label: 'Riesgo alto', value: count.alerta, color: STATUS.alerta.hex },
            ]} />
            <div className="grid grid-cols-3 gap-2 mt-3 text-center">
              {['normal', 'atencion', 'alerta'].map((k) => (
                <div key={k}>
                  <p className="text-xl font-bold" style={{ color: STATUS[k].hex }}>{count[k]}</p>
                  <p className="text-[11px] text-slate-500">{STATUS[k].label}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="card p-4 flex items-center gap-3">
            <Wifi className="w-5 h-5 text-ink-2" />
            <div className="text-sm">
              <p className="font-semibold text-ink">{online}/{workers.length} clips en línea</p>
              <Link to="/devices" className="back-link text-xs">Ver dispositivos <ArrowRight className="w-3 h-3" /></Link>
            </div>
          </div>
          <div className={`card p-4 flex items-center gap-3 ${incidents.length ? 'border-red-300' : ''}`}>
            <Siren className={`w-5 h-5 ${incidents.length ? 'text-red-600' : 'text-ink-2'}`} />
            <div className="text-sm">
              <p className="font-semibold text-ink">{incidents.length === 0 ? 'Sin incidentes de movimiento' : `${incidents.length} sin movimiento / caída`}</p>
              <Link to="/alerts" className="back-link text-xs">Ver alertas de seguridad <ArrowRight className="w-3 h-3" /></Link>
            </div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="section-heading">Requieren pausa preventiva</h2>
            <Link to="/workers" className="back-link">Ver todos <ArrowRight className="w-3 h-3" /></Link>
          </div>
          {top.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">Nadie requiere pausa en este momento.</p>
          ) : (
            <div className="space-y-2">
              {top.map((w) => (
                <div key={w.id} className="flex items-center gap-x-3 gap-y-2 flex-wrap p-2.5 rounded-xl border border-line">
                  <div className="flex-1 min-w-[140px]">
                    <Link to={`/workers/${w.id}`} className="text-sm font-semibold text-ink no-underline hover:text-heat-600">{w.name}</Link>
                    <p className="text-xs text-slate-500">{w.trade} · {ZONES.find((z) => z.id === w.zoneId).name}</p>
                  </div>
                  <RiskBar score={w.score} status={w.status} />
                  <StatusBadge status={workerStatus(w)} />
                  <button className="btn-primary btn-sm" title="Ordenar pausa" onClick={() => orderPause(w.id)}><Pause className="w-3.5 h-3.5" /></button>
                  <button className="btn-secondary btn-sm" title="Recordar hidratación" onClick={() => hydrate(w.id)}><Droplets className="w-3.5 h-3.5" /></button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="section-heading">Alertas abiertas</h2>
            <Link to="/alerts" className="back-link">Ver todas <ArrowRight className="w-3 h-3" /></Link>
          </div>
          {openAlerts.length === 0
            ? <p className="text-sm text-slate-500 py-6 text-center">Sin alertas abiertas.</p>
            : <div className="space-y-2">{openAlerts.map((a) => <AlertItem key={a.id} alert={a} compact />)}</div>}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <div className="flex items-center justify-between mb-1">
            <h2 className="section-heading">Hidratación pendiente</h2>
            <span className="text-xs text-slate-500">recordatorio cada {thresholds.hydrationMinutes} min</span>
          </div>
          <p className="text-xs text-slate-500 mb-3">Quienes no han presionado el botón del clip desde el intervalo configurado. Es un registro autodeclarado: no indica el estado de hidratación real.</p>
          {hydPending.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">Todos registraron hidratación dentro del intervalo.</p>
          ) : (
            <div className="space-y-2">
              {hydPending.slice(0, 6).map(({ w, st, since }) => (
                <div key={w.id} className="flex items-center gap-x-3 gap-y-2 flex-wrap p-2.5 rounded-xl border border-line">
                  <div className="flex-1 min-w-[140px]">
                    <Link to={`/workers/${w.id}`} className="text-sm font-semibold text-ink no-underline hover:text-heat-600">{w.name}</Link>
                    <p className="text-xs text-slate-500">último registro hace {since} min · {w.drinkCount} hoy</p>
                  </div>
                  <span className={`badge ${st === 'overdue' ? 'bg-amber-50 text-amber-800 border-amber-300' : 'bg-blue-50 text-blue-700 border-blue-200'}`}>{st === 'overdue' ? 'Sin registro' : 'Recordando'}</span>
                  <button className="btn-secondary btn-sm" title="Enviar recordatorio al clip" disabled={w.reminderSent} onClick={() => hydrate(w.id)}><BellRing className="w-3.5 h-3.5" />{w.reminderSent ? 'Enviado' : 'Recordar'}</button>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="card p-4">
          <h2 className="section-heading mb-3"><MousePointerClick className="w-4 h-4 text-ink-2" />Últimos registros del botón</h2>
          {hydEvents.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">Aún no hay registros en este turno.</p>
          ) : (
            <ul className="space-y-2">
              {hydEvents.map((e, i) => (
                <li key={`${e.workerId}-${e.clock}-${i}`} className="flex items-center gap-3 text-sm">
                  <span className="bg-cyan-50 text-cyan-700 rounded-lg p-1.5"><Droplets className="w-3.5 h-3.5" /></span>
                  <Link to={`/workers/${e.workerId}`} className="font-medium text-ink no-underline hover:text-heat-600 flex-1">{e.workerName}</Link>
                  <span className="text-xs text-slate-500">{fmtClock(e.clock)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div>
        <h2 className="section-heading mb-3">Zonas de la obra</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {ZONES.map((z) => {
            const inZone = workers.filter((w) => (z.kind === 'descanso' ? w.resting : w.zoneId === z.id && !w.resting));
            const worst = z.kind === 'descanso' ? null : inZone.reduce((m, w) => Math.max(m, STATUS_RANK[w.status]), 1);
            const color = z.kind === 'descanso' ? '#0891b2' : worst === 3 ? '#dc2626' : worst === 2 ? '#2563eb' : '#16a34a';
            const avgT = inZone.length ? inZone.reduce((a, w) => a + w.env.t, 0) / inZone.length : last.temp + z.tempOffset;
            return (
              <Link key={z.id} to="/map" className="card-interactive no-underline p-3.5 block" style={{ borderTop: `4px solid ${color}` }}>
                <p className="font-semibold text-sm text-ink">{z.name}</p>
                <p className="text-xs text-slate-500 line-clamp-1">{z.desc}</p>
                <div className="flex justify-between mt-2 text-xs text-slate-600">
                  <span><b className="text-ink">{inZone.length}</b> personas</span>
                  <span><b className="text-ink">{avgT.toFixed(1)}°</b> T. amb.</span>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
