import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Pause, Droplets, Thermometer, Gauge, Timer, Activity, Radio, HardHat, Siren, Footprints, BellRing, MousePointerClick } from 'lucide-react';
import { useApp } from '../context/AppContext';
import StatusBadge from '../components/StatusBadge';
import KpiCard from '../components/KpiCard';
import AlertItem from '../components/AlertItem';
import ClipLogo from '../components/ClipLogo';
import { LineChart, BatteryPill } from '../components/Charts';
import { ZONES } from '../data/seed';
import { fmtDuration, fmtClock, distanceKm, recentSteps } from '../lib/format';
import { hydrationState, sinceDrink, HYDRATION_BADGE, HYDRATION_LABEL } from '../lib/hydration';

export default function WorkerDetail() {
  const { workerId } = useParams();
  const { workers, alerts, clock, thresholds, orderPause, hydrate, registerDrink, attend, workerStatus } = useApp();
  const w = workers.find((x) => x.id === workerId);

  if (!w) {
    return <div className="page-layout"><Link to="/workers" className="back-link"><ArrowLeft className="w-4 h-4" />Volver</Link><p>Trabajador no encontrado.</p></div>;
  }
  const st = workerStatus(w);
  const zone = ZONES.find((z) => z.id === w.zoneId);
  const mine = alerts.filter((a) => a.workerId === w.id).slice(0, 6);
  const hs = hydrationState(w, clock, thresholds);
  const led = w.status;

  return (
    <div className="page-layout">
      <Link to="/workers" className="back-link"><ArrowLeft className="w-4 h-4" />Trabajadores</Link>

      <div className="card p-5 flex flex-wrap items-center gap-4 justify-between">
        <div className="flex items-center gap-4">
          <div className="bg-surface-2 rounded-2xl p-3 text-ink-2"><HardHat className="w-8 h-8" /></div>
          <div>
            <h1 className="text-xl font-extrabold text-ink">{w.name}</h1>
            <p className="text-sm text-slate-500">{w.trade} · {w.crew} · {zone.name}</p>
            <div className="mt-1.5 flex items-center gap-2"><StatusBadge status={st} pulse />
              {w.resting && <span className="text-xs text-cyan-700">pausa: {Math.max(0, w.restLeft)} min restantes</span>}
              <span className={`badge ${HYDRATION_BADGE[hs]}`}><Droplets className="w-3 h-3" />{HYDRATION_LABEL[hs]}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <ClipLogo active={led} className="w-24" />
          <button className="btn-primary" disabled={w.resting} onClick={() => orderPause(w.id)}><Pause className="w-4 h-4" />Ordenar pausa</button>
          <button className="btn-secondary" disabled={w.reminderSent} onClick={() => hydrate(w.id)}><BellRing className="w-4 h-4" />{w.reminderSent ? 'Recordatorio enviado' : 'Recordar hidratación'}</button>
          <button className="btn-secondary" title="Simula que el trabajador presiona el botón del clip" onClick={() => registerDrink(w.id)}><MousePointerClick className="w-4 h-4" />Simular botón del clip</button>
        </div>
      </div>

      {w.incident && (
        <div className="card border-red-300 bg-red-50/60 p-4 flex items-center gap-3 flex-wrap">
          <Siren className="w-6 h-6 text-red-600 shrink-0" />
          <div className="flex-1 min-w-[200px]">
            <p className="font-bold text-red-700">{w.incident.type === 'caida' ? 'Posible caída detectada' : `Sin movimiento hace ${w.stillMin} min`}</p>
            <p className="text-sm text-slate-600">El acelerómetro no registra movimiento desde las {fmtClock(w.incident.since)}. Verifica su estado en terreno.</p>
          </div>
          <button className="btn-primary" onClick={() => attend(w.id)}>Marcar como atendido</button>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <KpiCard icon={Gauge} label="Puntaje de riesgo" value={Math.round(w.score)} unit="/100" tone={w.status === 'alerta' ? 'red' : w.status === 'atencion' ? 'blue' : 'green'} hint={`atención ≥${thresholds.attention} · alto ≥${thresholds.alert}`} />
        <KpiCard icon={Thermometer} label="Temp. ambiente" value={w.env.t.toFixed(1)} unit="°C" tone="heat" hint="sensor del clip" />
        <KpiCard icon={Droplets} label="Humedad ambiente" value={Math.round(w.env.rh)} unit="%" tone="blue" hint="sensor del clip" />
        <KpiCard icon={Timer} label="Exposición acumulada" value={fmtDuration(w.exposure)} tone="navy" />
        <KpiCard icon={Activity} label="Actividad" value={Math.round(w.activity * 100)} unit="%" tone="green" hint={w.incident ? `sin movimiento ${w.stillMin} min` : 'acelerómetro'} />
        <KpiCard icon={Droplets} label="Última hidratación" value={`hace ${sinceDrink(w, clock)}`} unit="min" tone={hs === 'ok' ? 'blue' : 'heat'} hint={`${w.drinkCount} registros hoy · botón del clip`} />
        <KpiCard icon={Footprints} label="Recorrido (30 min)" value={distanceKm(w.history).toFixed(2)} unit="km" tone="navy" hint={`${recentSteps(w.history).toLocaleString('es-CL')} pasos · estimado`} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <h2 className="section-heading mb-2">Riesgo y actividad</h2>
          <LineChart data={w.history} yDomain={[0, 100]}
            lines={[{ key: 'score', label: 'Puntaje de riesgo', color: '#f97316' }, { key: 'act', label: 'Actividad (%)', color: '#0ea5e9' }]}
            refLines={[{ value: thresholds.attention, color: '#2563eb', label: 'Atención' }, { value: thresholds.alert, color: '#dc2626', label: 'Riesgo alto' }]} />
        </div>
        <div className="card p-4">
          <h2 className="section-heading mb-2">Temperatura ambiente</h2>
          <LineChart data={w.history} yDomain={[15, 50]}
            lines={[{ key: 'temp', label: 'Temp. ambiente', color: '#f97316', unit: '°C' }]}
            refLines={[{ value: 35, color: '#dc2626', label: '35°C alto riesgo' }]} />
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card p-4 space-y-3">
          <h2 className="section-heading"><Radio className="w-4 h-4 text-ink-2" />Dispositivo</h2>
          <dl className="text-sm grid grid-cols-2 gap-y-2">
            <dt className="text-slate-500">ID clip</dt><dd className="font-mono font-semibold">{w.deviceId}</dd>
            <dt className="text-slate-500">Montaje</dt><dd className="capitalize">{w.mount}</dd>
            <dt className="text-slate-500">Batería</dt><dd><BatteryPill level={w.battery} /></dd>
            <dt className="text-slate-500">Señal BLE</dt><dd>{Math.round(w.signal)} dBm</dd>
            <dt className="text-slate-500">Acelerómetro</dt><dd>{w.accel.toFixed(2)} g RMS</dd>
            <dt className="text-slate-500">Conexión</dt><dd>{w.online ? 'En línea' : 'Sin señal'}</dd>
            <dt className="text-slate-500">Botón (hidratación)</dt><dd>{`último ${fmtClock(w.hydratedAt)}`}</dd>
            <dt className="text-slate-500">Máx. riesgo hoy</dt><dd>{Math.round(w.worstToday)}</dd>
          </dl>
        </div>
        <div className="card p-4 lg:col-span-2 space-y-2">
          <h2 className="section-heading">Alertas recientes</h2>
          {mine.length === 0 ? <p className="text-sm text-slate-500 py-4">Sin alertas en este turno ({fmtClock(clock)}).</p>
            : mine.map((a) => <AlertItem key={a.id} alert={a} compact />)}
        </div>
      </div>
    </div>
  );
}
