import { Link } from 'react-router-dom';
import { AlertTriangle, Info, Radio, Siren, Check, CheckCheck, Pause, Droplets, BellRing } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { ZONES } from '../data/seed';
import { fmtClock } from '../lib/format';

const STATE_BADGE = {
  activa: 'bg-red-50 text-red-700 border-red-200',
  reconocida: 'bg-amber-50 text-amber-700 border-amber-200',
  resuelta: 'bg-slate-100 text-slate-500 border-slate-200',
};

export default function AlertItem({ alert, compact = false }) {
  const { orderPause, hydrate, ackAlert, resolveAlert, workers } = useApp();
  const zone = ZONES.find((z) => z.id === alert.zoneId);
  const crit = alert.level === 'alerta';
  const IconEl = alert.kind === 'dispositivo' ? Radio : alert.kind === 'seguridad' ? Siren : alert.kind === 'hidratacion' ? Droplets : crit ? AlertTriangle : Info;
  const worker = workers.find((w) => w.id === alert.workerId);

  return (
    <div className={`flex items-start gap-3 p-3 rounded-xl border ${alert.status === 'activa' && crit ? 'border-red-200 bg-red-50/40' : 'border-line bg-surface'}`}>
      <div className={`p-2 rounded-lg shrink-0 ${alert.kind === 'dispositivo' ? 'bg-slate-100 text-slate-600' : crit ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}`}>
        <IconEl className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Link to={`/workers/${alert.workerId}`} className="font-semibold text-sm text-ink no-underline hover:text-heat-600">{alert.workerName}</Link>
          <span className={`badge ${STATE_BADGE[alert.status]}`}>{alert.status}</span>
          {alert.kind !== 'dispositivo' && <span className={`badge ${crit ? 'bg-red-50 text-red-700 border-red-200' : 'bg-blue-50 text-blue-700 border-blue-200'}`}>{alert.kind === 'seguridad' ? 'Seguridad' : alert.kind === 'hidratacion' ? 'Hidratación' : crit ? 'Riesgo alto' : 'Atención'}</span>}
        </div>
        <p className="text-sm text-slate-600">{alert.reason}</p>
        <p className="meta-row mt-0.5">
          <span>{zone?.name}</span><span>· {fmtClock(alert.createdAt)}</span>
          {alert.kind === 'salud' && <span>· pico {Math.round(alert.peak)}</span>}
          {alert.action && <span className="text-green-700 font-medium">· {alert.action}</span>}
        </p>
      </div>
      {!compact && alert.status !== 'resuelta' && (
        <div className="flex flex-col sm:flex-row gap-1.5 shrink-0">
          {alert.kind === 'salud' && worker && !worker.resting && (
            <button className="btn-primary btn-sm" onClick={() => orderPause(alert.workerId)}><Pause className="w-3.5 h-3.5" />Pausa</button>
          )}
          {alert.kind === 'hidratacion' && worker && (
            <button className="btn-primary btn-sm" disabled={worker.reminderSent} onClick={() => hydrate(alert.workerId)}><BellRing className="w-3.5 h-3.5" />{worker.reminderSent ? 'Enviado' : 'Recordar'}</button>
          )}
          {alert.status === 'activa' && <button className="btn-secondary btn-sm" onClick={() => ackAlert(alert.id)}><Check className="w-3.5 h-3.5" />Reconocer</button>}
          <button className="btn-secondary btn-sm" onClick={() => resolveAlert(alert.id)}><CheckCheck className="w-3.5 h-3.5" />{alert.kind === 'seguridad' ? 'Atendido' : 'Resolver'}</button>
        </div>
      )}
    </div>
  );
}
