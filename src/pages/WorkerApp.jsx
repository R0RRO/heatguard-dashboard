import { useEffect, useMemo, useRef, useState } from 'react';
import { Bluetooth, BluetoothOff, RefreshCw, LogOut, Vibrate, Thermometer, Droplets, Activity, BatteryMedium, Signal, Server, Flame } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { createClipLink, bluetoothSupported } from '../lib/clipLink';
import { COMMAND } from '../lib/telemetry';
import { request, openStream } from '../lib/api';
import { STATE_CODES } from '../lib/simulation';
import { STATUS, DEFAULT_THRESHOLDS, personalFactor } from '../lib/risk';
import { heatIndexC, hiCategory } from '../lib/heatIndex';
import { WORKER_SEEDS } from '../data/seed';
import ThemeToggle from '../components/ThemeToggle';
import { movLevel, signalLevel } from '../lib/format';

const LINK_TEXT = { off: 'Clip sin vincular', connecting: 'Conectando con el clip…', connected: 'Clip vinculado', reconnecting: 'Se perdió el clip, reconectando…' };

function sendConfig(link, th) {
  link.send(COMMAND.setLoadLimit, Math.min(250, th.loadLimit));
  link.send(COMMAND.setTiredPct, th.tiredPct);
  link.send(COMMAND.setPauseMinutes, th.pauseMinutes);
  link.send(COMMAND.setAutoPause, th.autoPause ? 1 : 0);
}
const sendPersonal = (link, p) => p && link.send(COMMAND.setPersonalFactor, Math.round(personalFactor(p.heightCm, p.weightKg) * 100));

function instructions(code, m, th) {
  const left = Math.max(0, Math.ceil(th.pauseMinutes - (m?.stateS || 0) / 60));
  return {
    normal: '',
    cansancio: '',
    descanso: 'Mantén el botón 2 s para comenzar la pausa',
    pausa: `En pausa · quedan ${left} min`,
    finPausa: 'Mantén el botón 2 s para volver al trabajo',
  }[code];
}

// App del trabajador (Android, Chrome): vincula su clip por Bluetooth y reenvía las lecturas al supervisor
export default function WorkerApp() {
  const { user, token, logout } = useApp();
  const workerId = user.workerId;
  const seed = WORKER_SEEDS.find((w) => w.id === workerId);
  const [link, setLink] = useState({ status: 'off', deviceName: null, error: null });
  const [last, setLast] = useState(null);
  const [lastAt, setLastAt] = useState(0);
  const [stream, setStream] = useState('off');
  const [sent, setSent] = useState({ ok: 0, fail: 0 });
  const [notice, setNotice] = useState(null);
  const [now, setNow] = useState(() => Date.now());
  const linkRef = useRef(null);
  const thRef = useRef(DEFAULT_THRESHOLDS);
  const profRef = useRef(seed ? { heightCm: seed.heightCm, weightKg: seed.weightKg } : null);
  const [th, setTh] = useState(DEFAULT_THRESHOLDS);

  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);

  const post = useMemo(() => (path, body) => request(path, { token, method: 'POST', body }).catch((e) => {
    if (e.status === 401) logout();
    throw e;
  }), [token, logout]);

  // Enlace Bluetooth con el clip
  useEffect(() => {
    const l = createClipLink({
      onMessage: (msg) => {
        setLast(msg); setLastAt(Date.now());
        post('/api/telemetry', { workerId, msg })
          .then(() => setSent((s) => ({ ...s, ok: s.ok + 1 })))
          .catch(() => setSent((s) => ({ ...s, fail: s.fail + 1 })));
      },
      onStatus: (st) => {
        setLink({ status: st.status, deviceName: st.deviceName, error: st.error });
        if (st.status === 'off') setLast(null);
        post('/api/link', { workerId, link: st.status, device: st.deviceName || '' }).catch(() => {});
      },
    });
    linkRef.current = l;
    return () => l.disconnect();
  }, [workerId, post]);

  // Tiempo real desde el servidor: comandos del supervisor, umbrales y datos personales
  useEffect(() => {
    const es = openStream(token, {
      state: (d) => {
        thRef.current = { ...DEFAULT_THRESHOLDS, ...d.config }; setTh(thRef.current);
        if (d.profiles?.[workerId]) profRef.current = d.profiles[workerId];
        if (linkRef.current?.connected) { sendConfig(linkRef.current, thRef.current); sendPersonal(linkRef.current, profRef.current); }
      },
      config: (c) => { thRef.current = { ...thRef.current, ...c }; setTh(thRef.current); if (linkRef.current?.connected) sendConfig(linkRef.current, thRef.current); },
      profile: (p) => { profRef.current = p; if (linkRef.current?.connected) sendPersonal(linkRef.current, p); },
      command: (c) => {
        if (linkRef.current?.connected) linkRef.current.send(c.cmd, c.arg);
        const txt = { [COMMAND.pauseRequest]: 'El supervisor pidió una pausa de hidratación y descanso.', [COMMAND.cancelPauseRequest]: 'El supervisor retiró la solicitud de pausa.', [COMMAND.identify]: 'El supervisor está ubicando tu clip.' }[c.cmd];
        if (txt) { setNotice(txt); setTimeout(() => setNotice(null), 8000); }
        navigator.vibrate?.(200);
      },
    }, { workerId, onOpen: () => setStream('connected'), onError: () => setStream('reconnecting') });
    return () => es.close();
  }, [token, workerId]);

  // Mantener la pantalla encendida mientras el clip está vinculado (Android puede cortar el Bluetooth web en segundo plano)
  useEffect(() => {
    if (link.status === 'off' || !('wakeLock' in navigator)) return undefined;
    let lock = null;
    const get = () => navigator.wakeLock.request('screen').then((l) => { lock = l; }).catch(() => {});
    const onVis = () => { if (document.visibilityState === 'visible') get(); };
    get();
    document.addEventListener('visibilitychange', onVis);
    return () => { document.removeEventListener('visibilitychange', onVis); lock?.release().catch(() => {}); };
  }, [link.status]);

  const connect = async () => {
    try {
      await linkRef.current.connect();
      sendConfig(linkRef.current, thRef.current);
      sendPersonal(linkRef.current, profRef.current);
    } catch { /* el error queda en link.error */ }
  };

  const m = last;
  const fresh = m && now - lastAt < 8000;
  const code = m ? STATE_CODES[m.state] ?? 'normal' : null;
  const st = code && fresh ? STATUS[code] : STATUS.offline;
  const hi = m?.env.ok ? (m.env.heatIndexC ?? heatIndexC(m.env.tempC, m.env.rhPct)) : null;
  const cat = hi != null ? hiCategory(hi) : null;
  const tile = (Icon, label, value) => (
    <div className="bg-surface-2/70 rounded-xl p-3">
      <p className="text-[11px] text-slate-500 flex items-center gap-1"><Icon className="w-3.5 h-3.5" />{label}</p>
      <p className="text-lg font-bold text-ink">{value}</p>
    </div>
  );

  return (
    <div className="min-h-screen bg-surface-2/40">
      <header className="bg-navy-900 text-white px-4 py-3 flex items-center gap-3">
        <div className="bg-heat-500 rounded-lg p-1.5"><Flame className="w-4 h-4" /></div>
        <div className="flex-1 leading-tight">
          <p className="font-extrabold text-sm">HEATGUARD <span className="text-heat-400">CLIP</span></p>
          <p className="text-[11px] text-navy-200">{user.name}</p>
        </div>
        <ThemeToggle />
        <button onClick={logout} className="p-2 rounded-lg hover:bg-white/10 cursor-pointer" title="Cerrar sesión"><LogOut className="w-4 h-4" /></button>
      </header>

      <main className="max-w-md mx-auto p-4 space-y-4">
        {notice && <div className="rounded-xl bg-red-600 text-white px-4 py-3 text-sm font-semibold">{notice}</div>}

        <div className="card p-5 text-center space-y-3">
          <div className="mx-auto w-36 h-36 rounded-full flex items-center justify-center shadow-inner transition-colors"
            style={{ background: st.hex, boxShadow: `0 0 40px ${st.hex}66` }}>
            <div className="text-white">
              <p className="text-4xl font-extrabold">{m && fresh ? `${m.load}%` : '—'}</p>
              <p className="text-[11px] opacity-90">exposición acumulada</p>
            </div>
          </div>
          <p className="text-xl font-extrabold" style={{ color: st.hex }}>{m && fresh ? st.label : LINK_TEXT[link.status]}</p>
          {m && fresh && <p className="text-sm text-ink-2">{instructions(code, m, th)}</p>}
          {m && fresh && m.requestBySupervisor && code === 'descanso' && <p className="text-xs text-red-600 font-semibold">Pausa pedida por el supervisor</p>}
          {m && fresh && <p className="text-xs text-slate-500">LED del clip: {st.led} · pausas hoy: {m.pauses}</p>}
        </div>

        {m && (
          <div className="grid grid-cols-2 gap-3">
            {tile(Thermometer, 'Temperatura', m.env.ok ? `${m.env.tempC.toFixed(1)} °C` : 'sin sensor')}
            {tile(Droplets, 'Humedad', m.env.ok ? `${Math.round(m.env.rhPct)} %` : 'sin sensor')}
            {tile(Flame, `Sensación térmica${cat ? ` · ${cat.label}` : ''}`, hi != null ? `${hi.toFixed(1)} °C` : '—')}
            {tile(Activity, 'Movimiento', m.motion.ok ? movLevel(m.motion.index) : 'sin sensor')}
            {tile(BatteryMedium, 'Batería del clip', `${m.battery.pct} %`)}
            {tile(Signal, 'Señal', signalLevel(m.rssi))}
          </div>
        )}

        <div className="card p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm">
            {link.status === 'connected' ? <Bluetooth className="w-4 h-4 text-emerald-600" /> : link.status === 'off' ? <BluetoothOff className="w-4 h-4 text-slate-400" /> : <RefreshCw className="w-4 h-4 animate-spin text-amber-600" />}
            <span className="font-semibold text-ink">{LINK_TEXT[link.status]}</span>
            {link.deviceName && link.status !== 'off' && <span className="text-slate-500">· {link.deviceName}</span>}
          </div>
          {link.status === 'off'
            ? <button className="btn-primary w-full py-3 text-base" disabled={!bluetoothSupported()} onClick={connect}><Bluetooth className="w-5 h-5" />Vincular clip</button>
            : (
              <div className="flex gap-2">
                <button className="btn-secondary flex-1" onClick={() => linkRef.current.send(COMMAND.identify)}><Vibrate className="w-4 h-4" />Ubicar clip</button>
                <button className="btn-secondary flex-1" onClick={() => linkRef.current.disconnect()}>Desvincular</button>
              </div>
            )}
          {!bluetoothSupported() && <p className="text-xs text-amber-700">Este navegador no tiene Bluetooth web.</p>}
          {link.error && <p className="text-xs text-red-600">{link.error}</p>}
          <p className="text-xs text-slate-500 flex items-center gap-1.5">
            <Server className="w-3.5 h-3.5" />
            Servidor {stream === 'connected' ? 'en línea' : 'reconectando…'}
            {link.status !== 'off' && ` · ${sent.ok} lecturas enviadas${sent.fail ? `, ${sent.fail} fallidas` : ''}`}
          </p>
        </div>
      </main>
    </div>
  );
}
