// Motor de simulación de telemetría. Cada "tick" = 1 minuto simulado.
// La UI solo consume el objeto de estado que retornan createState/step. Un clip real conectado por
// Bluetooth reemplaza los valores simulados de su trabajador (ver tickLiveWorker y src/lib/telemetry.js).
//
// Regla central: NADIE se hidrata ni descansa por su cuenta. El clip (o el supervisor) solicita una pausa
// de hidratación y descanso; la pausa empieza y termina solo cuando el trabajador mantiene el botón.
import { SITE, ZONES, WORKER_SEEDS, SPARE_DEVICES } from '../data/seed.js';
import { clamp, loadRate, recoveryRate, computeStatus, mainReason, personalFactor } from './risk.js';
import { heatIndexC } from './heatIndex.js';

const HISTORY = 90;
const DAY = 24 * 60; // minutos simulados por día
const LOAD_MAX = 150; // tope de la exposición acumulada (%) mientras se espera que el trabajador acepte la pausa
const rnd = (a, b) => a + Math.random() * (b - a);
const noise = (s) => (Math.random() - 0.5) * 2 * s;
const zoneById = Object.fromEntries(ZONES.map((z) => [z.id, z]));
export const REST_ZONE = ZONES.find((z) => z.kind === 'descanso');
export const STATE_CODES = ['normal', 'cansancio', 'descanso', 'pausa', 'finPausa']; // código del clip → estado

function randomPointIn(zone) {
  const [s, w, n, e] = zone.bounds;
  const padLat = (n - s) * 0.12;
  const padLng = (e - w) * 0.12;
  return [rnd(s + padLat, n - padLat), rnd(w + padLng, e - padLng)];
}

// Clima base: mínimo ~06:00, máximo ~15:30. heatOffset simula ola de calor.
export function baseClimate(clock, heatOffset = 0) {
  const h = (clock % 1440) / 60;
  const s = Math.sin((2 * Math.PI * (h - 9.5)) / 24);
  return { t: 29.5 + 7.5 * s + heatOffset, rh: clamp(52 - 18 * s, 20, 85) };
}

const pauseElapsed = (w, clock) => (w.resting && w.pauseStart != null ? clock - w.pauseStart : 0);
const statusOf = (w, clock, th) => computeStatus({ load: w.load, resting: w.resting, pauseElapsed: pauseElapsed(w, clock), pauseReq: w.pauseReq }, th, w.status);

export function createState(th, heatOffset = 0) {
  const clock = 11 * 60 + 30;
  const workers = WORKER_SEEDS.map((seed, i) => {
    const zone = zoneById[seed.zoneId];
    const w = {
      ...seed,
      source: 'sim',      // 'sim' (simulado) | 'clip' (lecturas reales por Bluetooth)
      pos: randomPointIn(zone),
      target: randomPointIn(zone),
      activity: seed.intensity,
      load: rnd(0, 45),   // exposición acumulada (% del límite)
      resting: false,     // en pausa (empezó con el botón)
      pauseStart: null,
      pauseReq: null,     // { since, minutes, source: 'auto' | 'supervisor' }: el clip vibra hasta que se acepta
      pausesToday: 0,
      lastPauseEnd: clock - Math.round(rnd(20, 120)),
      lastPauseMin: 0,
      btnEvent: null,     // 'pausa-inicio' | 'pausa-fin' en este minuto
      autoRequested: false,
      compliance: i % 7 === 2 ? rnd(0.05, 0.1) : rnd(0.2, 0.5), // prob. por minuto de presionar el botón cuando el clip lo pide
      env: { t: 30, rh: 45, hi: 30, ok: true },
      status: 'normal',
      battery: rnd(48, 98),
      signal: rnd(-78, -50),
      online: true,
      offlineLeft: 0,
      history: [],
      peakLoad: 0,
      liveSeen: null,
    };
    // Pre-calentar lecturas para que los gráficos no partan vacíos (historia previa al inicio del demo)
    let cur = w;
    for (let k = HISTORY - 1; k >= 0; k--) cur = tickWorker(cur, clock - k, th, heatOffset, { silent: true });
    return { ...cur, pausesToday: cur.pausesToday, battery: w.battery - (i % 5) * 0.2, btnEvent: null };
  });

  const siteHistory = workers[0].history.map((pt, i) => {
    const c = { normal: 0, cansancio: 0, descanso: 0, pausa: 0 };
    workers.forEach((w) => { const st = w.history[i].st; c[st === 'finPausa' ? 'pausa' : st]++; });
    const clim = baseClimate(pt.clock, heatOffset);
    return { clock: pt.clock, temp: clim.t, rh: clim.rh, hi: heatIndexC(clim.t, clim.rh), ...c };
  });

  return { clock, workers, alerts: [], events: [], siteHistory, nextAlertId: 1, spare: SPARE_DEVICES };
}

function buildSiteSnapshot(state, heatOffset = 0) {
  const c = { normal: 0, cansancio: 0, descanso: 0, pausa: 0 };
  state.workers.forEach((w) => { c[w.status === 'finPausa' ? 'pausa' : w.status]++; });
  const clim = baseClimate(state.clock, heatOffset);
  return { clock: state.clock, temp: clim.t, rh: clim.rh, hi: heatIndexC(clim.t, clim.rh), ...c };
}

// Botón del clip mantenido 2 s: en pausa → la termina; si no → la comienza (solicitada o voluntaria).
export function holdButton(w, clock, th) {
  if (w.resting) {
    return {
      ...w, resting: false, pauseStart: null, lastPauseEnd: clock, lastPauseMin: clock - w.pauseStart,
      pausesToday: w.pausesToday + 1, btnEvent: 'pausa-fin', status: computeStatus({ load: w.load, resting: false, pauseReq: null }, th, null),
    };
  }
  return { ...w, resting: true, pauseStart: clock, pauseReq: null, btnEvent: 'pausa-inicio', status: 'pausa' };
}

function tickWorker(w, clock, th, heatOffset, { silent = false, live = null } = {}) {
  if (live) return tickLiveWorker(w, clock, th, live);
  const zone = zoneById[w.zoneId];
  const base = baseClimate(clock, heatOffset);
  const zoneRef = w.resting ? REST_ZONE : zone;
  const t = base.t + zoneRef.tempOffset + noise(0.25);
  const rh = clamp(base.rh + zoneRef.rhOffset + noise(1.5), 15, 95);
  const hi = heatIndexC(t, rh);

  // Movimiento (índice del acelerómetro, 0–1)
  let activity = w.activity;
  if (w.resting) activity += (0.05 - activity) * 0.4;
  else activity = clamp(activity + (w.intensity - activity) * 0.2 + noise(0.08), 0.1, 1);

  // Exposición acumulada: sube con calor y movimiento; baja solo durante la pausa
  const personal = personalFactor(w.heightCm, w.weightKg);
  let load = w.resting ? Math.max(0, w.load - recoveryRate(th)) : Math.min(LOAD_MAX, w.load + loadRate(hi, activity, th, personal));

  let next = { ...w, source: 'sim', liveSeen: null, activity, load, env: { t, rh, hi, ok: true }, btnEvent: null, autoRequested: false };

  // Al llegar al 100 % el clip solicita la pausa (rojo + 5 vibraciones cada 40 s)
  if (th.autoPause && !next.resting && !next.pauseReq && load >= 100) {
    next.pauseReq = { since: clock, minutes: th.pauseMinutes, source: 'auto' };
    next.autoRequested = !silent;
  }
  next.status = statusOf(next, clock, th);

  // Botón del clip (trabajadores simulados): solo responden cuando el clip lo pide.
  if (silent) {
    // Historia previa al demo: se asume que aceptaron y cerraron las pausas a tiempo
    if (next.pauseReq || (next.status === 'finPausa')) next = holdButton(next, clock, th);
  } else if (w.online && th.simResponds !== false) {
    const p = next.status === 'finPausa' ? 0.4 : next.pauseReq ? Math.min(0.8, w.compliance * 2) : 0;
    if (p > 0 && Math.random() < p) next = holdButton(next, clock, th);
  }
  next.status = statusOf(next, clock, th);

  // Posición en el mapa interno (zona de trabajo o de descanso)
  let target = w.target;
  let pos = w.pos;
  if (!silent) {
    const dest = next.resting ? REST_ZONE : zone;
    if (Math.random() < 0.15 || next.resting !== w.resting) target = randomPointIn(dest);
    pos = [w.pos[0] + (target[0] - w.pos[0]) * 0.35, w.pos[1] + (target[1] - w.pos[1]) * 0.35];
  }

  // Dispositivo
  let online = w.online;
  let offlineLeft = w.offlineLeft;
  if (!silent) {
    if (online && Math.random() < 0.004) { online = false; offlineLeft = Math.round(rnd(3, 8)); }
    else if (!online) { offlineLeft -= 1; if (offlineLeft <= 0) online = true; }
  }
  const battery = Math.max(0, w.battery - (silent ? 0 : 0.05));
  const signal = clamp(w.signal + noise(1.2), -95, -40);

  const point = { clock, temp: +t.toFixed(1), rh: Math.round(rh), hi: +hi.toFixed(1), load: Math.round(next.load), act: Math.round(activity * 100), st: next.status };
  return {
    ...next, pos, target, battery, signal, online, offlineLeft,
    history: [...w.history, point].slice(-HISTORY), peakLoad: Math.max(w.peakLoad, next.load),
  };
}

// Trabajador con clip real: el clip calcula la exposición acumulada y decide el estado; el panel solo lo muestra.
// dtMin son los minutos REALES desde el tick anterior.
function tickLiveWorker(w, clock, th, live) {
  const m = live.msg;
  if (!live.linked || !m) {
    const lastPt = w.history[w.history.length - 1];
    return { ...w, source: 'clip', online: false, btnEvent: null, autoRequested: false, history: [...w.history, { ...lastPt, clock }].slice(-HISTORY) };
  }
  const envOk = m.env.ok;
  const t = envOk ? m.env.tempC : w.env.t;
  const rh = envOk ? m.env.rhPct : w.env.rh;
  const hi = envOk ? heatIndexC(t, rh) : w.env.hi;
  const activity = m.motion.ok ? clamp(m.motion.index / 100) : 0;
  const status = STATE_CODES[m.state] ?? 'normal';
  const resting = status === 'pausa' || status === 'finPausa';
  const stateMin = Math.round(m.stateS / 60);

  // Eventos del botón: se detectan por el cambio de estado y por el contador de pausas del clip
  const first = w.liveSeen == null;
  let btnEvent = null;
  if (!first && resting && !w.resting) btnEvent = 'pausa-inicio';
  if (!first && !resting && w.resting) btnEvent = 'pausa-fin';
  const ended = first ? 0 : Math.max(0, m.pauses - w.liveSeen);

  // La espera de una pausa pedida se mide en minutos REALES (el reloj de la simulación puede ir acelerado)
  const dt = Math.max(0, live.dtMin || 0);
  let pauseReq = null;
  if (status === 'descanso') {
    const waitMin = (w.pauseReq?.waitMin ?? 0) + (w.status === 'descanso' ? dt : 0);
    pauseReq = {
      minutes: w.pauseReq?.minutes ?? th.pauseMinutes,
      source: m.requestBySupervisor ? 'supervisor' : (w.pauseReq?.source === 'supervisor' && w.status !== 'descanso' ? 'supervisor' : 'auto'),
      waitMin, since: clock - Math.round(waitMin),
    };
  }
  const autoRequested = !first && status === 'descanso' && w.status !== 'descanso' && pauseReq.source === 'auto';

  const point = { clock, temp: +t.toFixed(1), rh: Math.round(rh), hi: +hi.toFixed(1), load: Math.round(m.load), act: Math.round(activity * 100), st: status };
  return {
    ...w, source: 'clip', liveSeen: m.pauses, activity, load: m.load, status, resting, pauseReq, autoRequested,
    pauseStart: resting ? clock - stateMin : null,
    lastPauseEnd: !resting ? clock - stateMin : w.lastPauseEnd,
    lastPauseMin: btnEvent === 'pausa-fin' && w.pauseStart != null ? clock - w.pauseStart : w.lastPauseMin,
    pausesToday: w.pausesToday + ended,
    env: { t, rh, hi, ok: envOk }, signal: m.rssi, battery: m.battery.pct, online: true, offlineLeft: 0, btnEvent,
    history: [...w.history, point].slice(-HISTORY), peakLoad: Math.max(w.peakLoad, m.load),
  };
}

// live: { workerId, msg, linked, dtMin } por cada clip real conectado (uno o una lista; ver src/lib/telemetry.js)
export function step(prev, th, heatOffset = 0, live = null) {
  const clock = prev.clock + 1;
  const lives = Array.isArray(live) ? live : live ? [live] : [];
  let workers = prev.workers.map((w) => {
    const lv = lives.find((x) => x.workerId === w.id);
    if (lv) return tickWorker(w, clock, th, heatOffset, { live: lv });
    return tickWorker(w, clock, th, heatOffset);
  });

  let alerts = prev.alerts.map((a) => ({ ...a }));
  let events = prev.events;
  let nextAlertId = prev.nextAlertId;
  const newToasts = [];
  const open = (w, kind) => alerts.find((a) => a.workerId === w.id && a.kind === kind && a.status !== 'resuelta');
  const add = (w, kind, level, reason) => alerts.unshift({ id: nextAlertId++, kind, level, workerId: w.id, workerName: w.name, zoneId: w.zoneId, reason, status: 'activa', createdAt: clock, peak: Math.round(w.load) });

  workers.forEach((w) => {
    if (w.btnEvent) events = [{ type: w.btnEvent, clock, workerId: w.id, workerName: w.name }, ...events].slice(0, 40);
    if (w.autoRequested) {
      events = [{ type: 'pausa-solicitada', clock, workerId: w.id, workerName: w.name }, ...events].slice(0, 40);
      newToasts.push({ level: 'info', text: `${w.name}: toca descanso (exposición ${Math.round(w.load)} %). El clip pide la pausa.` });
    }

    // Toca descanso y no confirma la pausa en el clip
    const d = open(w, 'descanso');
    const waiting = w.pauseReq ? clock - w.pauseReq.since : 0;
    const dReason = `Toca descanso hace ${waiting} min y no ha comenzado la pausa en el clip`;
    if (w.pauseReq && w.online && waiting >= th.confirmMinutes && !d) add(w, 'descanso', 'alerta', dReason);
    else if (d && w.pauseReq) d.reason = dReason;
    else if (d) { d.status = 'resuelta'; d.resolvedAt = clock; d.action = w.resting ? 'Pausa comenzada con el botón' : 'Solicitud retirada'; }

    // Pausa cumplida y sin cerrar con el botón
    const pc = open(w, 'pausa');
    const over = w.status === 'finPausa' ? clock - w.pauseStart - th.pauseMinutes : 0;
    const pReason = `Pausa cumplida hace ${over} min y sin cerrar en el clip`;
    if (w.status === 'finPausa' && w.online && over >= th.confirmMinutes && !pc) add(w, 'pausa', 'atencion', pReason);
    else if (pc && w.status === 'finPausa') pc.reason = pReason;
    else if (pc) { pc.status = 'resuelta'; pc.resolvedAt = clock; pc.action = 'Pausa cerrada con el botón'; }

    // Dispositivo
    const dev = open(w, 'dispositivo');
    const devIssue = !w.online ? 'Clip sin conexión' : !w.env.ok ? 'Sensor de temperatura y humedad sin respuesta' : w.battery < 15 ? `Batería baja (${Math.round(w.battery)}%)` : null;
    if (devIssue && !dev) add(w, 'dispositivo', 'atencion', devIssue);
    else if (devIssue && dev) dev.reason = devIssue;
    else if (!devIssue && dev) { dev.status = 'resuelta'; dev.resolvedAt = clock; }
  });

  alerts = alerts.slice(0, 200);

  // Cambio de día (00:00 del reloj simulado): los contadores «de hoy» parten de cero y los clips
  // simulados amanecen cargados (se cargan de noche); la batería del clip real es la que informa el clip.
  if (Math.floor(clock / DAY) !== Math.floor(prev.clock / DAY)) {
    workers = workers.map((w, i) => ({
      ...w, pausesToday: 0, peakLoad: w.load,
      battery: w.source === 'clip' ? w.battery : 88 + ((i * 7) % 13),
    }));
    events = [];
    alerts = alerts.filter((a) => a.status !== 'resuelta');
  }

  const next = { ...prev, clock, workers, alerts, events, nextAlertId };
  next.siteHistory = [...prev.siteHistory, buildSiteSnapshot(next, heatOffset)].slice(-HISTORY);
  return { state: next, toasts: newToasts };
}

// ─── Acciones del supervisor ────────────────────────────────────────────
// Solicitar una pausa: el clip pasa a rojo y vibra (5 pulsos cada 40 s) hasta que el trabajador mantiene
// el botón. El panel NO pone a nadie en pausa directamente.
export function orderPause(state, workerId, minutes = 15) {
  return {
    ...state,
    workers: state.workers.map((w) =>
      w.id === workerId && !w.resting
        ? { ...w, pauseReq: { since: w.pauseReq?.since ?? state.clock, minutes, source: 'supervisor' }, status: 'descanso' }
        : w,
    ),
  };
}

// Altura y peso del trabajador (influyen en la exposición acumulada a través del factor personal)
export function setProfile(state, workerId, { heightCm, weightKg }) {
  return { ...state, workers: state.workers.map((w) => (w.id === workerId ? { ...w, heightCm, weightKg } : w)) };
}

export function cancelPause(state, workerId, th) {
  return {
    ...state,
    workers: state.workers.map((w) => (w.id === workerId && w.pauseReq
      ? { ...w, pauseReq: null, status: computeStatus({ load: w.load, resting: false, pauseReq: null }, th, w.status) }
      : w)),
  };
}

// Botón del clip mantenido, simulado desde el panel (solo trabajadores simulados)
export function pressButton(state, workerId, th) {
  let event = null;
  const workers = state.workers.map((w) => {
    if (w.id !== workerId) return w;
    const next = holdButton(w, state.clock, th);
    event = next.btnEvent;
    return { ...next, btnEvent: null };
  });
  const w = workers.find((x) => x.id === workerId);
  return {
    ...state, workers,
    events: event ? [{ type: event, clock: state.clock, workerId, workerName: w?.name }, ...state.events].slice(0, 40) : state.events,
  };
}

export function ackAlert(state, alertId) {
  return {
    ...state,
    alerts: state.alerts.map((a) => (a.id === alertId && a.status === 'activa' ? { ...a, status: 'reconocida', ackAt: state.clock } : a)),
  };
}

export function resolveAlert(state, alertId) {
  return {
    ...state,
    alerts: state.alerts.map((a) => (a.id === alertId && a.status !== 'resuelta' ? { ...a, status: 'resuelta', resolvedAt: state.clock } : a)),
  };
}

export { SITE, ZONES, mainReason };
