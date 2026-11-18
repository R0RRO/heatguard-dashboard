import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Pause, Thermometer, Gauge, Droplets, BatteryMedium, Activity, Radio, HardHat, MousePointerClick, Coffee, Timer, Sun } from 'lucide-react';
import { useApp } from '../context/AppContext';
import StatusBadge from '../components/StatusBadge';
import KpiCard from '../components/KpiCard';
import AlertItem from '../components/AlertItem';
import ClipLogo from '../components/ClipLogo';
import { LineChart, BatteryPill } from '../components/Charts';
import { ZONES } from '../data/seed';
import { fmtClock, fmtDuration } from '../lib/format';
import { hiCategory, HI_REF_LINES } from '../lib/heatIndex';
import { STATUS, loadRate, heatFactor, personalFactor } from '../lib/risk';
import SourceBadge from '../components/SourceBadge';
import HeatIndexBadge from '../components/HeatIndexBadge';
import PauseBadge from '../components/PauseBadge';
import ProfileCard from '../components/ProfileCard';
import { buttonAction } from '../lib/buttonEvents';
import { movLevel, signalDetail } from '../lib/format';
import WbgtBadge from '../components/WbgtBadge';
import { heatLevel, hasWbgt, HEAT_FACTOR, WBGT_REF_LINES } from '../lib/risk';

export default function WorkerDetail() {
  const { workerId } = useParams();
  const { workers, alerts, clock, thresholds, orderPause, cancelPause, pressButton, workerStatus } = useApp();
  const w = workers.find((x) => x.id === workerId);

  if (!w) {
    return <div className="page-layout"><Link to="/workers" className="back-link"><ArrowLeft className="w-4 h-4" />Volver</Link><p>Trabajador no encontrado.</p></div>;
  }
  const st = workerStatus(w);
  const zone = ZONES.find((z) => z.id === w.zoneId);
  const mine = alerts.filter((a) => a.workerId === w.id).slice(0, 6);
  const live = w.source === 'clip';
  const hiCat = hiCategory(w.env.hi);
  const personal = personalFactor(w.heightCm, w.weightKg);
  const heat = heatLevel(w);
  const rate = loadRate(w.env.hi, w.activity, thresholds, personal, heat.source === 'wbgt' ? heat.level : null);
  const toLimit = !w.resting && w.load < 100 ? (100 - w.load) / rate : null;
  const statusTone = { normal: 'green', cansancio: 'heat', descanso: 'red', pausa: 'blue', finPausa: 'blue', offline: 'navy' }[st];

  return (
    <div className="page-layout">
      {live && <div className="rounded-xl bg-emerald-50 border-2 border-emerald-400 text-emerald-800 px-4 py-2 text-sm font-semibold">Clip real</div>}
      <Link to="/workers" className="back-link"><ArrowLeft className="w-4 h-4" />Trabajadores</Link>

      <div className="card p-5 flex flex-wrap items-center gap-4 justify-between">
        <div className="flex items-center gap-4">
          <div className="bg-surface-2 rounded-2xl p-3 text-ink-2"><HardHat className="w-8 h-8" /></div>
          <div>
            <h1 className="text-xl font-extrabold text-ink">{w.name}</h1>
            <p className="text-sm text-slate-500">{w.trade} · {w.crew} · {zone.name}</p>
            <div className="mt-1.5 flex items-center gap-2 flex-wrap">
              <StatusBadge status={st} pulse /><SourceBadge source={w.source} /><PauseBadge w={w} clock={clock} />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <ClipLogo active={w.status} className="w-24" />
          {w.pauseReq
            ? <button className="btn-secondary" onClick={() => cancelPause(w.id)}><Pause className="w-4 h-4" />Retirar solicitud</button>
            : <button className="btn-primary" disabled={w.resting} onClick={() => orderPause(w.id, thresholds.pauseMinutes)}><Pause className="w-4 h-4" />Solicitar pausa</button>}
          {!live && <button className="btn-secondary" onClick={() => pressButton(w.id)}><MousePointerClick className="w-4 h-4" />Simular botón: {buttonAction(w)}</button>}
        </div>
      </div>

      <div className="card p-3 text-sm text-slate-600 flex items-center gap-3 flex-wrap">
        <span className="font-semibold text-ink">LED del clip:</span>
        <span style={{ color: STATUS[w.status].hex }} className="font-semibold">{STATUS[w.status].led}</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <KpiCard icon={BatteryMedium} label="Exposición acumulada" value={Math.round(w.load)} unit="%" tone={statusTone} hint={w.resting ? 'bajando durante la pausa' : `+${rate.toFixed(1)} %/min · factor personal ×${personal.toFixed(1)}`} />
        <KpiCard icon={Timer} label="Hasta el límite" value={toLimit == null ? '—' : fmtDuration(toLimit)} tone="navy" hint={toLimit == null ? (w.resting ? 'en pausa' : 'límite alcanzado') : 'al ritmo actual'} />
        <KpiCard icon={Coffee} label="Pausas hoy" value={w.pausesToday} tone="blue" hint={w.resting ? `en pausa hace ${Math.max(0, clock - w.pauseStart)} min` : `última terminó hace ${Math.max(0, clock - w.lastPauseEnd)} min`} />
        {hasWbgt(w)
          ? <KpiCard icon={Sun} label="WBGT estimado (modelo Ono)" value={w.wbgt.c.toFixed(1)} unit="°C" tone="heat" hint={`${w.wbgt.label} · factor ×${HEAT_FACTOR[w.wbgt.level]} · radiación ${w.wbgt.solarWm2} W/m² · viento ${w.wbgt.windMs} m/s (Open-Meteo)`} />
          : null}
        <KpiCard icon={Gauge} label="Sensación térmica (Heat Index)" value={w.env.hi.toFixed(1)} unit="°C" tone="heat" hint={hasWbgt(w) ? `${hiCat.label} · referencia` : `${hiCat.label} · factor ×${heatFactor(w.env.hi)} (sin WBGT)`} />
        <KpiCard icon={Thermometer} label="Temp. del aire" value={w.env.t.toFixed(1)} unit="°C" tone="heat" hint={w.env.ok ? 'sensor del clip' : 'sensor sin respuesta · último valor'} />
        <KpiCard icon={Droplets} label="Humedad relativa" value={Math.round(w.env.rh)} unit="%" tone="blue" hint={w.env.ok ? 'sensor del clip' : 'sensor sin respuesta · último valor'} />
        <KpiCard icon={Activity} label="Índice de movimiento" value={Math.round(w.activity * 100)} unit="/100" tone="green" hint={`${movLevel(w.activity * 100).toLowerCase()} · acelerómetro · sin validar`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <h2 className="section-heading mb-2">Exposición acumulada y movimiento</h2>
          <LineChart data={w.history} yDomain={[0, 120]}
            lines={[{ key: 'load', label: 'Exposición acumulada (%)', color: '#f97316' }, { key: 'act', label: 'Índice de movimiento', color: '#0ea5e9' }]}
            refLines={[{ value: thresholds.tiredPct, color: STATUS.cansancio.hex, label: 'Cansancio' }, { value: 100, color: STATUS.descanso.hex, label: 'Toca descanso' }]} />
        </div>
        <div className="card p-4">
          <h2 className="section-heading mb-2">Temperatura, sensación térmica y WBGT estimado {hasWbgt(w) ? <WbgtBadge wbgt={w.wbgt} /> : <HeatIndexBadge hi={w.env.hi} />}</h2>
          <LineChart data={w.history} yDomain={[15, 55]}
            lines={[{ key: 'temp', label: 'Temp. del aire', color: '#f97316', unit: ' °C' }, { key: 'hi', label: 'Sensación térmica (Heat Index)', color: '#7c3aed', unit: ' °C' }, { key: 'wbgt', label: 'WBGT estimado', color: '#dc2626', unit: ' °C', dashed: true }]}
            refLines={hasWbgt(w) ? WBGT_REF_LINES : HI_REF_LINES} />
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <ProfileCard key={w.id} w={w} />
        <div className="card p-4 space-y-3">
          <h2 className="section-heading"><Radio className="w-4 h-4 text-ink-2" />Dispositivo</h2>
          <dl className="text-sm grid grid-cols-2 gap-y-2">
            <dt className="text-slate-500">ID clip</dt><dd className="font-mono font-semibold">{w.deviceId}</dd>
            <dt className="text-slate-500">Montaje</dt><dd className="capitalize">{w.mount}</dd>
            <dt className="text-slate-500">Batería</dt><dd><BatteryPill level={w.battery} /></dd>
            <dt className="text-slate-500">Datos</dt><dd><SourceBadge source={w.source} /></dd>
            <dt className="text-slate-500">Señal BLE</dt><dd>{signalDetail(w.signal)}</dd>
            <dt className="text-slate-500">Conexión</dt><dd>{w.online ? 'En línea' : 'Sin señal'}</dd>
            <dt className="text-slate-500">Exposición máx. hoy</dt><dd>{Math.round(w.peakLoad)} %</dd>
          </dl>
        </div>
        <div className="card p-4 space-y-2">
          <h2 className="section-heading">Alertas recientes</h2>
          {mine.length === 0 ? <p className="text-sm text-slate-500 py-4">Sin alertas en este turno ({fmtClock(clock)}).</p>
            : mine.map((a) => <AlertItem key={a.id} alert={a} compact />)}
        </div>
      </div>
    </div>
  );
}
