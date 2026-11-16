import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { createState as createSim, step, orderPause, cancelPause, pressButton, ackAlert, resolveAlert, setProfile } from '../lib/simulation';
import { DEFAULT_THRESHOLDS, displayStatus, personalFactor } from '../lib/risk';
import { createClipLink, bluetoothSupported } from '../lib/clipLink';
import { COMMAND } from '../lib/telemetry';
import { loadSession, saveSession, request, apiLogin, openStream } from '../lib/api';

// Configuración que el clip usa para decidir su estado por sí solo
function sendConfig(link, th) {
  link.send(COMMAND.setLoadLimit, Math.min(250, th.loadLimit));
  link.send(COMMAND.setTiredPct, th.tiredPct);
  link.send(COMMAND.setPauseMinutes, th.pauseMinutes);
  link.send(COMMAND.setAutoPause, th.autoPause ? 1 : 0);
}

// Factor personal (altura y peso) del trabajador que lleva el clip real
function sendPersonal(link, w) {
  if (w) link.send(COMMAND.setPersonalFactor, Math.round(personalFactor(w.heightCm, w.weightKg) * 100));
}

// Altura y peso editados en el panel, guardados en este navegador
const PROFILES_KEY = 'hg_profiles';
function createState(th, heat) {
  const s = createSim(th, heat);
  const profiles = load(PROFILES_KEY, {});
  return { ...s, workers: s.workers.map((w) => (profiles[w.id] ? { ...w, ...profiles[w.id] } : w)) };
}

const LINK_FRESH_MS = 8000;
const HISTORY_KEEP = 90;  // puntos de historia por trabajador (igual que src/lib/simulation.js) // sin lecturas en este tiempo, el clip real se muestra sin señal

const AppContext = createContext(null);

const load = (key, fallback) => {
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch { return fallback; }
};
const save = (key, value) => {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* sin storage */ }
};

export function AppProvider({ children }) {
  // Sesión: { token, user } del servidor, o { token: null, user } en modo demo (sin servidor)
  const [session, setSession] = useState(loadSession);
  const user = session?.user || null;
  const token = session?.token || null;
  // admin y supervisor ven el panel; el admin además configura (en modo demo, sin servidor, todo está permitido)
  const isSupervisor = user?.role === 'supervisor' || user?.role === 'admin';
  const isAdmin = user?.role === 'admin' || !!user?.demo;
  const [usersVersion, setUsersVersion] = useState(0);
  const serverMode = !!token && isSupervisor;   // la simulación corre en el servidor y la comparten todos
  const [server, setServer] = useState({ status: 'off', error: null }); // conexión en tiempo real con el servidor
  const [thresholds, setThresholdsLocal] = useState(() => ({ ...DEFAULT_THRESHOLDS, ...load('hg_thresholds', {}) }));
  const [heatOffset, setHeatOffsetLocal] = useState(0);
  const [running, setRunningLocal] = useState(true);
  const [speed, setSpeedLocal] = useState(1); // ticks por intervalo (1x = 1.5 s por minuto simulado)
  const [toasts, setToasts] = useState([]);
  const [theme, setTheme] = useState(() => {
    const saved = load('hg_theme', null);
    if (saved) return saved;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    save('hg_theme', theme);
  }, [theme]);

  const thRef = useRef(thresholds);
  const heatRef = useRef(heatOffset);
  const [sim, setSim] = useState(() => createState(thresholds, heatOffset));
  const simRef = useRef(sim);
  const tickCount = useRef(0);

  useEffect(() => { thRef.current = thresholds; save('hg_thresholds', thresholds); }, [thresholds]);

  // Cambios de umbrales hechos en este panel: con servidor se guardan allá y llegan a todos los clips
  const putTimer = useRef(null);
  const setThresholds = useCallback((upd) => {
    const next = typeof upd === 'function' ? upd(thRef.current) : upd;
    thRef.current = next;
    setThresholdsLocal(next);
    if (token) {
      clearTimeout(putTimer.current);
      putTimer.current = setTimeout(() => request('/api/config', { token, method: 'PUT', body: next }).catch(() => {}), 400);
    }
  }, [token]);
  useEffect(() => { heatRef.current = heatOffset; }, [heatOffset]);

  const pushToasts = useCallback((list) => {
    if (!list.length) return;
    const withIds = list.slice(0, 1).map((t) => ({ ...t, id: Math.random().toString(36).slice(2) }));
    setToasts((prev) => [...prev, ...withIds.filter((t) => !prev.some((x) => x.text === t.text))].slice(-4));
    withIds.forEach((t) => setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== t.id)), 6000));
  }, []);

  // ── Clip real por Bluetooth: sus lecturas reemplazan a las simuladas del trabajador asignado ──
  const [clip, setClip] = useState(() => ({
    supported: bluetoothSupported(), status: 'off', deviceName: null, error: null, lost: 0, invalid: 0,
    workerId: load('hg_clip_worker', 'w1'), last: null, lastAt: 0, count: 0,
  }));
  const tokenRef = useRef(null);
  useEffect(() => { tokenRef.current = token && isSupervisor ? token : null; }, [token, isSupervisor]);
  const liveRef = useRef({ active: false, msg: null, at: 0, tickAt: 0, workerId: clip.workerId });
  const linkRef = useRef(null);
  useEffect(() => {
    const link = createClipLink({
      onMessage: (msg) => {
        if (tokenRef.current) request('/api/telemetry', { token: tokenRef.current, method: 'POST', body: { workerId: liveRef.current.workerId, msg } }).catch(() => {});
        liveRef.current.msg = msg;
        liveRef.current.at = msg.receivedAt;
        setClip((c) => ({ ...c, last: msg, lastAt: msg.receivedAt, count: c.count + 1, error: null }));
      },
      onStatus: (st) => {
        if (tokenRef.current) request('/api/link', { token: tokenRef.current, method: 'POST', body: { workerId: liveRef.current.workerId, link: st.status, device: st.deviceName || '' } }).catch(() => {});
        liveRef.current.active = st.status !== 'off';
        if (st.status === 'off') liveRef.current.msg = null;
        setClip((c) => ({ ...c, ...st, last: st.status === 'off' ? null : c.last }));
      },
    });
    linkRef.current = link;
    return () => link.disconnect();
  }, []);

  // ── Clips reales enlazados por los celulares de los trabajadores (llegan desde el servidor) ──
  const remoteRef = useRef({});   // workerId → { msg, recvAt, link, device, tickAt }
  const simTicks = useRef(0);
  const toastRef = useRef(null);
  useEffect(() => { toastRef.current = pushToasts; }, [pushToasts]);
  const [remote, setRemote] = useState({});
  const applyRef = useRef(null);
  useEffect(() => {
    if (!token || !isSupervisor) return undefined;
    const now = () => Date.now();
    const setLive = (id, v) => {
      const prev = remoteRef.current[id] || {};
      const fresh = v.msg && v.at && v.at !== prev.at;
      remoteRef.current = {
        ...remoteRef.current,
        [id]: { ...prev, link: v.link, device: v.device, by: v.by, msg: v.msg ?? prev.msg, at: v.at, recvAt: fresh ? now() : prev.recvAt || 0, tickAt: prev.tickAt || now() },
      };
      setRemote(remoteRef.current);
    };
    const applyProfiles = (profiles) => applyRef.current?.((st) => Object.entries(profiles || {}).reduce((acc, [id, p]) => setProfile(acc, id, p), st));
    const es = openStream(token, {
      state: (d) => {
        thRef.current = { ...thRef.current, ...d.config };
        setThresholdsLocal(thRef.current);
        applyProfiles(d.profiles);
        remoteRef.current = {};
        // lecturas antiguas no cuentan como enlace vivo
        for (const [id, v] of Object.entries(d.live || {})) setLive(id, { ...v, at: v.at && now() - v.at < LINK_FRESH_MS ? v.at : 0 });
        setRemote(remoteRef.current);
      },
      config: (c) => { thRef.current = { ...thRef.current, ...c }; setThresholdsLocal(thRef.current); },
      users: () => setUsersVersion((v) => v + 1),
      simfull: (d) => {
        const { ctl, ...st } = d;
        simRef.current = st; setSim(st);
        setRunningLocal(ctl.running); setSpeedLocal(ctl.speed); setHeatOffsetLocal(ctl.heatOffset);
        simTicks.current = 0;
      },
      sim: (d) => {
        const prev = simRef.current;
        const byId = Object.fromEntries(prev.workers.map((w) => [w.id, w]));
        const workers = d.workers.map(({ points, ...w }) => ({ ...w, history: [...(byId[w.id]?.history || []), ...points].slice(-HISTORY_KEEP) }));
        const siteHistory = [...prev.siteHistory, ...d.sitePoints].slice(-HISTORY_KEEP);
        simRef.current = { ...prev, clock: d.clock, workers, alerts: d.alerts, events: d.events, spare: d.spare, nextAlertId: d.nextAlertId, siteHistory };
        setSim(simRef.current);
        setRunningLocal(d.ctl.running); setSpeedLocal(d.ctl.speed); setHeatOffsetLocal(d.ctl.heatOffset);
        simTicks.current += 1;
        if (simTicks.current > 3 && d.toasts?.length) toastRef.current?.(d.toasts);
      },
      profile: (p) => applyProfiles({ [p.workerId]: p }),
      live: (v) => setLive(v.workerId, v),
    }, {
      onOpen: () => setServer({ status: 'connected', error: null }),
      onError: () => {
        setServer({ status: 'reconnecting', error: null });
        request('/api/me', { token }).catch((e) => { if (e.status === 401) { saveSession(null); setSession(null); } });
      },
    });
    return () => { es.close(); setServer({ status: 'off', error: null }); };
  }, [token, isSupervisor]);

  const clipActions = useMemo(() => ({
    connectClip: async () => {
      try {
        await linkRef.current.connect();
        liveRef.current.tickAt = Date.now();
        sendConfig(linkRef.current, thRef.current);
        sendPersonal(linkRef.current, simRef.current.workers.find((w) => w.id === liveRef.current.workerId));
      } catch { /* el error queda en clip.error */ }
    },
    disconnectClip: () => linkRef.current.disconnect(),
    assignClip: (workerId) => {
      liveRef.current.workerId = workerId;
      save('hg_clip_worker', workerId);
      setClip((c) => ({ ...c, workerId }));
      sendPersonal(linkRef.current, simRef.current.workers.find((w) => w.id === workerId));
    },
    identifyClip: () => linkRef.current.send(COMMAND.identify),
  }), []);

  // La configuración de exposición y pausas del panel se envía al clip real (el clip decide su estado con ella)
  useEffect(() => { if (linkRef.current) sendConfig(linkRef.current, thresholds); }, [thresholds]);

  useEffect(() => {
    if (!running || !isSupervisor || serverMode) return undefined;
    const id = setInterval(() => {
      let allToasts = [];
      const lr = liveRef.current;
      const now = Date.now();
      const live = [];
      if (lr.active) live.push({ workerId: lr.workerId, msg: lr.msg, linked: !!lr.msg && now - lr.at < LINK_FRESH_MS, dtMin: lr.tickAt ? (now - lr.tickAt) / 60000 : 0 });
      lr.tickAt = now;
      for (const [id, r] of Object.entries(remoteRef.current)) {
        if (r.link === 'off' || (lr.active && lr.workerId === id)) continue;
        live.push({ workerId: id, msg: r.msg, linked: !!r.msg && now - r.recvAt < LINK_FRESH_MS, dtMin: (now - r.tickAt) / 60000 });
        r.tickAt = now;
      }
      for (let i = 0; i < speed; i++) {
        const { state, toasts: tt } = step(simRef.current, thRef.current, heatRef.current, i === 0 ? live : live.map((l) => ({ ...l, dtMin: 0 })));
        simRef.current = state;
        allToasts = allToasts.concat(tt);
      }
      setSim(simRef.current);
      tickCount.current += speed;
      // evita ráfaga de avisos al iniciar la simulación
      if (tickCount.current > 6) pushToasts(allToasts);
    }, 1500);
    return () => clearInterval(id);
  }, [running, speed, user, isSupervisor, serverMode, pushToasts]);

  const apply = useCallback((fn) => {
    simRef.current = fn(simRef.current);
    setSim(simRef.current);
  }, []);
  useEffect(() => { applyRef.current = apply; }, [apply]);

  // Comando para el clip de un trabajador: por Bluetooth si está enlazado a este navegador, si no por el servidor (celular)
  const sendCommand = useCallback((id, cmd, arg = 0) => {
    if (liveRef.current.active && liveRef.current.workerId === id) { linkRef.current.send(cmd, arg); return; }
    const r = remoteRef.current[id];
    if (token && r && r.link !== 'off') request('/api/command', { token, method: 'POST', body: { workerId: id, cmd, arg } }).catch(() => {});
  }, [token]);

  // En modo servidor las acciones van a la simulación compartida (y el servidor avisa al clip real del celular)
  const simAction = useCallback((body) => request('/api/sim', { token, method: 'POST', body })
    .catch((e) => pushToasts([{ level: 'alerta', text: e.message }])), [token, pushToasts]);
  const localClip = (id) => liveRef.current.active && liveRef.current.workerId === id;

  const actions = useMemo(() => ({
    orderPause: (id, min = 15) => {
      if (serverMode) { simAction({ action: 'orderPause', workerId: id, minutes: min }); if (localClip(id)) linkRef.current.send(COMMAND.pauseRequest, min); }
      else { apply((s) => orderPause(s, id, min)); sendCommand(id, COMMAND.pauseRequest, min); }
      const w = simRef.current.workers.find((x) => x.id === id);
      pushToasts([{ level: 'ok', text: `Pausa solicitada a ${w?.name}` }]);
    },
    cancelPause: (id) => {
      if (serverMode) { simAction({ action: 'cancelPause', workerId: id }); if (localClip(id)) linkRef.current.send(COMMAND.cancelPauseRequest); }
      else { apply((s) => cancelPause(s, id, thRef.current)); sendCommand(id, COMMAND.cancelPauseRequest); }
      const w = simRef.current.workers.find((x) => x.id === id);
      pushToasts([{ level: 'ok', text: `Solicitud de pausa retirada (${w?.name})` }]);
    },
    setWorkerProfile: (id, profile) => {
      apply((s) => setProfile(s, id, profile));
      if (token) request(`/api/profile/${id}`, { token, method: 'PUT', body: profile }).catch(() => {});
      else save(PROFILES_KEY, { ...load(PROFILES_KEY, {}), [id]: profile });
      const w = simRef.current.workers.find((x) => x.id === id);
      if (liveRef.current.active && liveRef.current.workerId === id) sendPersonal(linkRef.current, w);
      pushToasts([{ level: 'ok', text: `Datos de ${w?.name} guardados` }]);
    },
    pressButton: (id) => {
      if (serverMode) { simAction({ action: 'pressButton', workerId: id }); return; }
      apply((s) => pressButton(s, id, thRef.current));
      const ev = simRef.current.events[0];
      const msg = { 'pausa-inicio': 'comenzó su pausa de hidratación y descanso', 'pausa-fin': 'terminó su pausa' }[ev?.type];
      if (ev?.workerId === id && msg) pushToasts([{ level: 'ok', text: `${ev.workerName} ${msg} (botón del clip)` }]);
    },
    ackAlert: (id) => (serverMode ? simAction({ action: 'ackAlert', alertId: id }) : apply((s) => ackAlert(s, id))),
    resolveAlert: (id) => (serverMode ? simAction({ action: 'resolveAlert', alertId: id }) : apply((s) => resolveAlert(s, id))),
    resetSim: () => {
      if (serverMode) { simAction({ action: 'reset' }); return; }
      simRef.current = createState(thRef.current, heatRef.current);
      setSim(simRef.current);
    },
    identifyWorkerClip: (id) => (serverMode && !localClip(id) ? simAction({ action: 'identify', workerId: id }) : sendCommand(id, COMMAND.identify)),
    // Controles de la simulación: en modo servidor cambian la simulación de todos
    setRunning: (v) => (serverMode ? simAction({ action: 'control', running: v }) : setRunningLocal(v)),
    setSpeed: (v) => (serverMode ? simAction({ action: 'control', speed: v }) : setSpeedLocal(v)),
    setHeatOffset: (v) => (serverMode ? simAction({ action: 'control', heatOffset: v }) : setHeatOffsetLocal(v)),
  }), [apply, pushToasts, sendCommand, token, serverMode, simAction]);

  const startSession = (s) => { saveSession(s); setSession(s); };
  // Al abrir, se actualizan rol y clip asignado desde el servidor (pueden haber cambiado)
  useEffect(() => {
    if (!token) return;
    request('/api/me', { token })
      .then(({ user: u }) => setSession((prev) => {
        if (!prev || prev.token !== token) return prev;
        const next = { ...prev, user: u };
        saveSession(next);
        return next;
      }))
      .catch((e) => { if (e.status === 401) { saveSession(null); setSession(null); } });
  }, [token]);
  const login = async (usuario, clave) => startSession(await apiLogin(usuario, clave));
  const loginDemo = () => startSession({ token: null, user: { name: 'Modo demo', role: 'supervisor', demo: true } });
  const logout = () => {
    if (token) request('/api/logout', { token, method: 'POST' }).catch(() => {});
    startSession(null);
  };

  // Clips reales visibles en el panel: el enlazado a este navegador y los enlazados por celulares
  const liveClips = useMemo(() => {
    const list = [];
    if (clip.status !== 'off') list.push({ workerId: clip.workerId, via: 'bluetooth', status: clip.status, last: clip.last, lastAt: clip.lastAt, deviceName: clip.deviceName });
    for (const [id, r] of Object.entries(remote)) {
      if (r.link === 'off' || list.some((l) => l.workerId === id)) continue;
      list.push({ workerId: id, via: 'celular', status: r.link, last: r.msg, lastAt: r.recvAt, deviceName: r.device, by: r.by });
    }
    return list;
  }, [clip, remote]);
  const liveIds = useMemo(() => liveClips.map((l) => l.workerId), [liveClips]);

  const value = {
    user, token, isAdmin, usersVersion, login, loginDemo, logout, server, remote, liveClips, liveIds,
    theme, toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
    sim, workers: sim.workers, alerts: sim.alerts, clock: sim.clock, siteHistory: sim.siteHistory, events: sim.events,
    thresholds, setThresholds,
    heatOffset, running, speed,
    toasts, dismissToast: (id) => setToasts((p) => p.filter((t) => t.id !== id)),
    ...actions,
    clip, ...clipActions,
    workerStatus: displayStatus,
  };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const useApp = () => useContext(AppContext);
