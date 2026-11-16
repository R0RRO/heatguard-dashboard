import { Link } from 'react-router-dom';
import { Users, Hourglass, BatteryMedium, Thermometer, Gauge, Coffee, Pause, ArrowRight, Wifi, MousePointerClick } from 'lucide-react';
import { useApp } from '../context/AppContext';
import KpiCard from '../components/KpiCard';
import SimControls from '../components/SimControls';
import AlertItem from '../components/AlertItem';
import PauseBadge from '../components/PauseBadge';
import { LineChart, StackedArea, Donut, LoadBar } from '../components/Charts';
import { ZONES, SITE } from '../data/seed';
import { STATUS, STATUS_RANK } from '../lib/risk';
import { fmtClock } from '../lib/format';
import { hiCategory, HI_REF_LINES } from '../lib/heatIndex';
import { BUTTON_EVENT } from '../lib/buttonEvents';
import { useStableOrder } from '../hooks/useStableOrder';

export default function Dashboard() {
  const { workers, alerts, siteHistory, clock, thresholds, orderPause, cancelPause, events, liveIds } = useApp();
  const isLive = (id) => liveIds.includes(id);

  const count = { normal: 0, cansancio: 0, descanso: 0, pausa: 0 };
  workers.forEach((w) => count[w.status === 'finPausa' ? 'pausa' : w.status]++);
  const online = workers.filter((w) => w.online).length;
  const last = siteHistory[siteHistory.length - 1];
  const hiCat = hiCategory(last.hi);
  const pausesToday = workers.reduce((a, w) => a + w.pausesToday, 0);

  const firstPinned = (a, b) => isLive(b.id) - isLive(a.id);
  const waiting = workers.filter((w) => w.pauseReq).sort((a, b) => firstPinned(a, b) || a.pauseReq.since - b.pauseReq.since);
  const resting = workers.filter((w) => w.resting).sort((a, b) => firstPinned(a, b) || a.pauseStart - b.pauseStart);
  const nearLimit = useStableOrder(workers.filter((w) => !w.resting && !w.pauseReq && w.status === 'cansancio').sort((a, b) => firstPinned(a, b) || b.load - a.load)).slice(0, 6);
  const openAlerts = alerts.filter((a) => a.status !== 'resuelta').slice(0, 5);
  const btnEvents = events.filter((e) => BUTTON_EVENT[e.type]).slice(0, 8);

  const row = (w, children) => (
    <div key={w.id} className={`flex items-center gap-x-3 gap-y-2 flex-wrap p-2.5 rounded-xl ${isLive(w.id) ? 'live-card' : 'border border-line'}`}>
      <div className="flex-1 min-w-[140px]">
        <Link to={`/workers/${w.id}`} className="text-sm font-semibold text-ink no-underline hover:text-heat-600">{w.name}</Link>
        {isLive(w.id) && <span className="ml-2 badge bg-emerald-600 text-white border-emerald-600">Clip real</span>}
        <p className="text-xs text-slate-500">{w.trade} · {ZONES.find((z) => z.id === w.zoneId).name}</p>
      </div>
      {children}
    </div>
  );

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
        <KpiCard icon={Users} label="Trabajadores en obra" value={workers.length} hint={`${online} clips en línea`} />
        <KpiCard icon={Hourglass} label="Toca descanso" value={count.descanso} tone="red" hint="pausa solicitada, sin comenzar" />
        <KpiCard icon={BatteryMedium} label="Con cansancio" value={count.cansancio} tone="heat" hint={`exposición ≥ ${thresholds.tiredPct} %`} />
        <KpiCard icon={Coffee} label="En pausa" value={count.pausa} tone="blue" hint={`${pausesToday} pausas completadas hoy`} />
        <KpiCard icon={Thermometer} label="Temp. del aire" value={last.temp.toFixed(1)} unit="°C" tone="heat" hint={`humedad ${Math.round(last.rh)}%`} />
        <KpiCard icon={Gauge} label="Sensación térmica (Heat Index)" value={last.hi.toFixed(1)} unit="°C" tone="heat" hint={`${hiCat.label} · indicador auxiliar`} />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card p-4 lg:col-span-2 space-y-4">
          <div>
            <h2 className="section-heading mb-2">Evolución del estado de la cuadrilla</h2>
            <StackedArea data={siteHistory} series={[
              { key: 'normal', label: STATUS.normal.label, color: STATUS.normal.hex },
              { key: 'cansancio', label: STATUS.cansancio.label, color: STATUS.cansancio.hex },
              { key: 'descanso', label: STATUS.descanso.label, color: STATUS.descanso.hex },
              { key: 'pausa', label: STATUS.pausa.label, color: STATUS.pausa.hex },
            ]} />
          </div>
          <div>
            <h2 className="section-heading mb-2">Temperatura del aire y sensación térmica (Heat Index) de la obra</h2>
            <LineChart data={siteHistory} yDomain={[15, 55]}
              lines={[{ key: 'temp', label: 'Temp. del aire', color: '#f97316', unit: ' °C' }, { key: 'hi', label: 'Sensación térmica (Heat Index)', color: '#7c3aed', unit: ' °C' }]}
              refLines={HI_REF_LINES} />
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-4">
            <h2 className="section-heading mb-3">Estado actual</h2>
            <Donut center={{ value: workers.length, label: 'trabajadores' }} segments={['normal', 'cansancio', 'descanso', 'pausa'].map((k) => (
              { label: STATUS[k].label, value: count[k], color: STATUS[k].hex }
            ))} />
            <div className="grid grid-cols-4 gap-1 mt-3 text-center">
              {['normal', 'cansancio', 'descanso', 'pausa'].map((k) => (
                <div key={k}>
                  <p className="text-xl font-bold" style={{ color: STATUS[k].hex }}>{count[k]}</p>
                  <p className="text-[11px] text-slate-500 leading-tight">{STATUS[k].label}</p>
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
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <div className="flex items-center justify-between mb-1">
            <h2 className="section-heading">Toca descanso</h2>
            <Link to="/workers" className="back-link">Ver todos <ArrowRight className="w-3 h-3" /></Link>
          </div>
          {waiting.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">Nadie tiene una pausa pendiente.</p>
          ) : (
            <div className="space-y-2">
              {waiting.slice(0, 6).map((w) => row(w, <>
                <LoadBar load={w.load} status={w.status} />
                <PauseBadge w={w} clock={clock} />
                {w.pauseReq.source === 'supervisor' && <button className="btn-secondary btn-sm" onClick={() => cancelPause(w.id)}>Retirar</button>}
              </>))}
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

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card p-4">
          <h2 className="section-heading mb-1">Cerca del límite</h2>
          {nearLimit.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">Nadie con cansancio en este momento.</p>
          ) : (
            <div className="space-y-2">
              {nearLimit.map((w) => row(w, <>
                <LoadBar load={w.load} status={w.status} />
                <button className="btn-primary btn-sm" onClick={() => orderPause(w.id, thresholds.pauseMinutes)}><Pause className="w-3.5 h-3.5" /></button>
              </>))}
            </div>
          )}
        </div>

        <div className="card p-4">
          <h2 className="section-heading mb-1">En pausa</h2>
          {resting.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">Nadie en pausa.</p>
          ) : (
            <div className="space-y-2">{resting.slice(0, 6).map((w) => row(w, <PauseBadge w={w} clock={clock} />))}</div>
          )}
        </div>

        <div className="card p-4">
          <h2 className="section-heading mb-1"><MousePointerClick className="w-4 h-4 text-ink-2" />Registro de pausas</h2>
          {btnEvents.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">Aún no hay registros en este turno.</p>
          ) : (
            <ul className="space-y-2">
              {btnEvents.map((e, i) => (
                <li key={`${e.workerId}-${e.clock}-${i}`} className="flex items-center gap-3 text-sm">
                  <span className={`${BUTTON_EVENT[e.type].tone} rounded-lg p-1.5`}>{e.type === 'pausa-solicitada' ? <Hourglass className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}</span>
                  <Link to={`/workers/${e.workerId}`} className="font-medium text-ink no-underline hover:text-heat-600 flex-1">{e.workerName}</Link>
                  <span className="text-xs text-slate-500">{BUTTON_EVENT[e.type].label}</span>
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
            const worst = z.kind === 'descanso' ? null : inZone.reduce((m, w) => Math.max(m, STATUS_RANK[w.status] ?? 0), 1);
            const color = z.kind === 'descanso' ? STATUS.pausa.hex : worst === 3 ? STATUS.descanso.hex : worst === 2 ? STATUS.cansancio.hex : STATUS.normal.hex;
            const avgT = inZone.length ? inZone.reduce((a, w) => a + w.env.t, 0) / inZone.length : last.temp + z.tempOffset;
            return (
              <div key={z.id} className="card p-3.5" style={{ borderTop: `4px solid ${color}` }}>
                <p className="font-semibold text-sm text-ink">{z.name}</p>
                <p className="text-xs text-slate-500 line-clamp-1">{z.desc}</p>
                <div className="flex justify-between mt-2 text-xs text-slate-600">
                  <span><b className="text-ink">{inZone.length}</b> personas</span>
                  <span><b className="text-ink">{avgT.toFixed(1)}°</b> T. amb.</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
