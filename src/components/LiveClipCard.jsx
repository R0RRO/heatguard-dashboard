import { useEffect, useState } from 'react';
import { Bluetooth, BluetoothOff, RefreshCw, Vibrate } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { heatIndexC } from '../lib/heatIndex';
import HeatIndexBadge from './HeatIndexBadge';
import StatusBadge from './StatusBadge';
import { STATE_CODES } from '../lib/simulation';
import { movDetail, signalDetail } from '../lib/format';

const STATUS_TEXT = {
  off: 'Sin clip conectado',
  connecting: 'Conectando…',
  connected: 'Conectado',
  reconnecting: 'Se perdió el enlace, reconectando…',
};

// Conexión de un clip real por Bluetooth. Sus lecturas reemplazan a las simuladas del trabajador elegido.
export default function LiveClipCard() {
  const { clip, workers, connectClip, disconnectClip, assignClip, identifyClip } = useApp();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const on = clip.status !== 'off';
  const m = clip.last;
  const age = m ? Math.max(0, Math.round((now - clip.lastAt) / 1000)) : null;
  const hi = m?.env.ok ? heatIndexC(m.env.tempC, m.env.rhPct) : null;
  const cell = (label, value, hint) => (
    <div className="bg-surface-2/60 rounded-lg px-3 py-2 min-w-[110px]">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="text-sm font-semibold text-ink">{value}</p>
      {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
    </div>
  );

  return (
    <div className={`card p-4 space-y-3 ${clip.status === 'connected' ? 'border-emerald-300' : ''}`}>
      <div className="flex items-center gap-3 flex-wrap">
        <div className={`rounded-lg p-2.5 ${clip.status === 'connected' ? 'bg-emerald-50 text-emerald-600' : 'bg-surface-2 text-ink-2'}`}>
          {on ? <Bluetooth className="w-5 h-5" /> : <BluetoothOff className="w-5 h-5" />}
        </div>
        <div className="flex-1 min-w-[200px]">
          <h2 className="section-heading">Clip real por Bluetooth</h2>
          <p className="text-xs text-slate-500">
            {STATUS_TEXT[clip.status]}{clip.deviceName && on ? ` · ${clip.deviceName}` : ''}
            {clip.status === 'reconnecting' && <RefreshCw className="inline w-3 h-3 ml-1 animate-spin" />}
          </p>
        </div>
        <label className="text-xs text-slate-500 flex items-center gap-2">
          Asignado a
          <select className="form-select" value={clip.workerId} onChange={(e) => assignClip(e.target.value)}>
            {workers.map((w) => <option key={w.id} value={w.id}>{w.name} ({w.deviceId})</option>)}
          </select>
        </label>
        {on && <button className="btn-secondary btn-sm" onClick={identifyClip} title="El clip parpadea y vibra"><Vibrate className="w-3.5 h-3.5" />Ubicar</button>}
        {on
          ? <button className="btn-secondary" onClick={disconnectClip}>Desconectar</button>
          : <button className="btn-primary" disabled={!clip.supported} onClick={connectClip}><Bluetooth className="w-4 h-4" />Conectar clip</button>}
      </div>

      {!clip.supported && <p className="text-xs text-amber-700">Este navegador no tiene Bluetooth web.</p>}
      {clip.error && <p className="text-xs text-red-600">{clip.error}</p>}

      {m ? (
        <div className="flex gap-2 flex-wrap">
          {cell('Temperatura', m.env.ok ? `${m.env.tempC.toFixed(1)} °C` : '—', m.env.ok ? 'aire' : 'sensor sin respuesta')}
          {cell('Humedad', m.env.ok ? `${m.env.rhPct.toFixed(0)} %` : '—', 'relativa')}
          <div className="bg-surface-2/60 rounded-lg px-3 py-2 min-w-[150px]">
            <p className="text-[11px] text-slate-500">Sensación térmica (Heat Index)</p>
            <p className="text-sm font-semibold text-ink">{hi != null ? `${hi.toFixed(1)} °C` : '—'}</p>
            <HeatIndexBadge hi={hi} />
          </div>
          {cell('Movimiento', m.motion.ok ? movDetail(m.motion.index) : '—', m.motion.ok ? null : 'acelerómetro sin respuesta')}
          {cell('Batería', `${m.battery.pct} %`, `${(m.battery.mV / 1000).toFixed(2)} V`)}
          {cell('Señal BLE', signalDetail(m.rssi))}
          <div className="bg-surface-2/60 rounded-lg px-3 py-2 min-w-[150px]">
            <p className="text-[11px] text-slate-500">Estado del clip</p>
            <p className="text-sm font-semibold text-ink">Exposición {m.load} %</p>
            <StatusBadge status={STATE_CODES[m.state]} pulse />
          </div>
          {cell('Pausas', `${m.pauses} completadas`, m.state >= 3 ? `en pausa hace ${Math.round(m.stateS / 60)} min` : `última hace ${Math.round(m.stateS / 60)} min`)}
          {cell('Última lectura', `hace ${age} s`, `n.º ${m.seq} · ${clip.lost} perdidas · ${clip.invalid} descartadas`)}
        </div>
      ) : null}
    </div>
  );
}
