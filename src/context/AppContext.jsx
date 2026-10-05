import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { createState, step, orderPause, hydrate, ackAlert, resolveAlert, attendWorker } from '../lib/simulation';
import { DEFAULT_THRESHOLDS, displayStatus } from '../lib/risk';

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
  const [user, setUser] = useState(() => load('hg_user', null));
  const [thresholds, setThresholds] = useState(() => ({ ...DEFAULT_THRESHOLDS, ...load('hg_thresholds', {}) }));
  const [heatOffset, setHeatOffset] = useState(0);
  const [running, setRunning] = useState(true);
  const [speed, setSpeed] = useState(1); // ticks por intervalo (1x = 1.5 s por minuto simulado)
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
  useEffect(() => { heatRef.current = heatOffset; }, [heatOffset]);

  const pushToasts = useCallback((list) => {
    if (!list.length) return;
    const withIds = list.slice(0, 1).map((t) => ({ ...t, id: Math.random().toString(36).slice(2) }));
    setToasts((prev) => [...prev, ...withIds.filter((t) => !prev.some((x) => x.text === t.text))].slice(-4));
    withIds.forEach((t) => setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== t.id)), 6000));
  }, []);

  useEffect(() => {
    if (!running || !user) return undefined;
    const id = setInterval(() => {
      let allToasts = [];
      for (let i = 0; i < speed; i++) {
        const { state, toasts: tt } = step(simRef.current, thRef.current, heatRef.current);
        simRef.current = state;
        allToasts = allToasts.concat(tt);
      }
      setSim(simRef.current);
      tickCount.current += speed;
      // evita ráfaga de avisos al iniciar la simulación
      if (tickCount.current > 6) pushToasts(allToasts);
    }, 1500);
    return () => clearInterval(id);
  }, [running, speed, user, pushToasts]);

  const apply = useCallback((fn) => {
    simRef.current = fn(simRef.current);
    setSim(simRef.current);
  }, []);

  const actions = useMemo(() => ({
    orderPause: (id, min) => {
      apply((s) => orderPause(s, id, min));
      const w = simRef.current.workers.find((x) => x.id === id);
      pushToasts([{ level: 'ok', text: `Pausa ordenada a ${w?.name}` }]);
    },
    hydrate: (id) => {
      apply((s) => hydrate(s, id));
      const w = simRef.current.workers.find((x) => x.id === id);
      pushToasts([{ level: 'ok', text: `Recordatorio de hidratación enviado a ${w?.name}` }]);
    },
    attend: (id) => {
      apply((s) => attendWorker(s, id));
      const w = simRef.current.workers.find((x) => x.id === id);
      pushToasts([{ level: 'ok', text: `${w?.name} marcado como atendido` }]);
    },
    ackAlert: (id) => apply((s) => ackAlert(s, id)),
    resolveAlert: (id) => apply((s) => resolveAlert(s, id)),
    resetSim: () => {
      simRef.current = createState(thRef.current, heatRef.current);
      setSim(simRef.current);
    },
  }), [apply, pushToasts]);

  const login = (u) => { setUser(u); save('hg_user', u); };
  const logout = () => { setUser(null); save('hg_user', null); };

  const value = {
    user, login, logout,
    theme, toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
    sim, workers: sim.workers, alerts: sim.alerts, clock: sim.clock, siteHistory: sim.siteHistory,
    thresholds, setThresholds,
    heatOffset, setHeatOffset, running, setRunning, speed, setSpeed,
    toasts, dismissToast: (id) => setToasts((p) => p.filter((t) => t.id !== id)),
    ...actions,
    workerStatus: displayStatus,
  };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const useApp = () => useContext(AppContext);
