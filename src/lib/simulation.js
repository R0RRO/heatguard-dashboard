// Motor de simulación de telemetría. Cada "tick" = 1 minuto simulado.
// Sustituir por lecturas reales (WebSocket / API) cuando exista backend:
// la UI solo consume el objeto de estado que retorna createState/step.
import { SITE, ZONES, WORKER_SEEDS, SPARE_DEVICES } from '../data/seed';
import { apparentTemp, riskScore, statusFromScore, mainReason, clamp } from './risk';
import { sinceDrink, hydrationState, DEFAULT_HYDRATION_MINUTES } from './hydration';

const HISTORY = 90;
const rnd = (a, b) => a + Math.random() * (b - a);
const noise = (s) => (Math.random() - 0.5) * 2 * s;
const zoneById = Object.fromEntries(ZONES.map((z) => [z.id, z]));
export const REST_ZONE = ZONES.find((z) => z.kind === 'descanso');

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

export function createState(th, heatOffset = 0) {
  const clock = 11 * 60 + 30;
  const workers = WORKER_SEEDS.map((seed, i) => {
    const zone = zoneById[seed.zoneId];
    const exposure = rnd(0, 25);
    const w = {
      ...seed,
      pos: randomPointIn(zone),
      target: randomPointIn(zone),
      activity: seed.intensity,
      resting: false,
      restLeft: 0,
      incident: null, // { type: 'caida' | 'inmovil', since }
      stillMin: 0,
      accel: 0,
      // Botón de hidratación del clip
      hydratedAt: clock - Math.round(rnd(0, 38)),
      drinks: [],
      drinkCount: Math.round(rnd(1, 4)),
      reminderSent: false,
      compliance: i % 7 === 2 ? rnd(0.01, 0.025) : rnd(0.06, 0.2), // prob. por minuto de presionar el botón con el recordatorio activo
      env: { t: 30, rh: 45 },
      exposure,
      score: 0,
      status: 'normal',
      factors: {},
      battery: rnd(48, 98),
      signal: rnd(-78, -50),
      online: true,
      offlineLeft: 0,
      history: [],
      worstToday: 0,
    };
    // pre-calentar algunas lecturas para que el gráfico no parta vacío
    let cur = w;
    for (let k = HISTORY - 1; k >= 0; k--) {
      cur = tickWorker(cur, clock - k, th, heatOffset, { silent: true });
    }
    return { ...cur, battery: w.battery - (i % 5) * 0.2 };
  });

  const siteHistory = workers[0].history.map((pt, i) => {
    const c = { normal: 0, atencion: 0, alerta: 0 };
    workers.forEach((w) => { c[statusFromScore(w.history[i].score, th)]++; });
    const clim = baseClimate(pt.clock, heatOffset);
    return {
      clock: pt.clock, temp: clim.t,
      rh: clim.rh, ...c,
    };
  });

  return { clock, workers, alerts: [], events: [], siteHistory, nextAlertId: 1, spare: SPARE_DEVICES };
}

function buildSiteSnapshot(state, heatOffset = 0) {
  const ws = state.workers;
  const c = { normal: 0, atencion: 0, alerta: 0 };
  ws.forEach((w) => c[w.status]++);
  const clim = baseClimate(state.clock, heatOffset);
  return {
    clock: state.clock,
    temp: clim.t,
    rh: clim.rh,
    ...c,
  };
}

function tickWorker(w, clock, th, heatOffset, { silent = false } = {}) {
  const zone = zoneById[w.zoneId];
  const base = baseClimate(clock, heatOffset);
  const inRest = w.resting;
  const zoneRef = inRest ? REST_ZONE : zone;
  const t = base.t + zoneRef.tempOffset + noise(0.25);
  const rh = clamp(base.rh + zoneRef.rhOffset + noise(1.5), 15, 95);
  const at = apparentTemp(t, rh);

  // Actividad
  let activity = w.activity;
  let restLeft = w.restLeft;
  let resting = w.resting;
  if (resting) {
    activity += (0.05 - activity) * 0.4;
    restLeft -= 1;
  } else {
    activity = clamp(activity + (w.intensity - activity) * 0.2 + noise(0.08), 0.1, 1);
  }
  // Incidente (caída / inmovilidad): el acelerómetro no registra movimiento
  if (w.incident) {
    resting = false;
    restLeft = 0;
    activity = clamp(0.02 + noise(0.015), 0, 0.06);
  }

  // Exposición acumulada (min-equivalentes de calor)
  let exposure = w.exposure;
  if (resting) exposure = Math.max(0, exposure - 1.8);
  else exposure += at > 32 ? 0.8 : at > 28 ? 0.5 : 0.2;

  const { score, factors } = riskScore({ at, exposure, activity });
  const status = statusFromScore(score, th);

  // Pausa espontánea (descansos normales) y retorno al trabajo
  let target = w.target;
  let pos = w.pos;
  if (!silent) {
    if (!resting && !w.incident && status === 'atencion' && Math.random() < 0.04) {
      resting = true;
      restLeft = Math.round(rnd(10, 18));
    }
    if (resting && restLeft <= 0 && score < th.attention) {
      resting = false;
    }
    const dest = resting ? REST_ZONE : zone;
    if (Math.random() < 0.15 || resting !== w.resting) target = randomPointIn(dest);
    pos = [w.pos[0] + (target[0] - w.pos[0]) * 0.35, w.pos[1] + (target[1] - w.pos[1]) * 0.35];
    if (w.incident) { target = w.pos; pos = w.pos; }
  }

  // Botón de hidratación: con el recordatorio activo el trabajador tiende a presionarlo
  let { hydratedAt, drinks, drinkCount, reminderSent } = w;
  let pressed = false;
  if (!silent && w.online && !w.incident) {
    const limit = th.hydrationMinutes ?? DEFAULT_HYDRATION_MINUTES;
    if (clock - hydratedAt >= limit) {
      const p = w.compliance * (resting ? 3 : 1) * (reminderSent ? 3 : 1);
      if (Math.random() < p) {
        pressed = true;
        hydratedAt = clock;
        drinks = [...drinks, clock].slice(-12);
        drinkCount += 1;
        reminderSent = false;
      }
    }
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

  const point = { clock, temp: +t.toFixed(1), rh: Math.round(rh), score: Math.round(score), act: Math.round(activity * 100), st: Math.round(clamp(activity * 70 + noise(4), 0, 200)) };
  const accel = +(activity * 0.9 + Math.random() * 0.03).toFixed(2); // g RMS simulado
  const history = [...w.history, point].slice(-HISTORY);

  return {
    ...w, pos, target, activity, accel, resting, restLeft, exposure,
    env: { t, rh }, score, factors, status, battery, signal, online, offlineLeft,
    hydratedAt, drinks, drinkCount, reminderSent, pressed,
    history, worstToday: Math.max(w.worstToday, score),
  };
}

export function step(prev, th, heatOffset = 0) {
  const clock = prev.clock + 1;
  let workers = prev.workers.map((w) => {
    const next = tickWorker(w, clock, th, heatOffset);
    if (!next.incident && !next.resting && next.online && Math.random() < 0.0006) {
      next.incident = { type: Math.random() < 0.5 ? 'caida' : 'inmovil', since: clock };
      next.stillMin = 0;
    } else if (next.incident) {
      next.stillMin = w.incident ? w.stillMin + 1 : 0;
      if (next.incident.type === 'inmovil' && clock - next.incident.since >= 20) { next.incident = null; next.stillMin = 0; }
    }
    // Pausa automática recomendada (opcional)
    if (th.autoPause && !next.resting && next.status === 'alerta' && Math.random() < 0.25) {
      next.resting = true;
      next.restLeft = 15;
      next.target = randomPointIn(REST_ZONE);
    }
    return next;
  });

  // Alertas
  let alerts = prev.alerts.map((a) => ({ ...a }));
  let events = prev.events;
  let nextAlertId = prev.nextAlertId;
  const newToasts = [];

  workers.forEach((w) => {
    if (w.pressed) events = [{ type: 'hidratacion', clock, workerId: w.id, workerName: w.name }, ...events].slice(0, 40);

    // Alerta de hidratación: pasó el recordatorio sin registro
    const hyd = alerts.find((a) => a.workerId === w.id && a.kind === 'hidratacion' && a.status !== 'resuelta');
    const hState = hydrationState(w, clock, th);
    const since = sinceDrink(w, clock);
    if (hState === 'overdue' && w.online && !hyd) {
      alerts.unshift({
        id: nextAlertId++, kind: 'hidratacion', level: 'atencion', workerId: w.id, workerName: w.name,
        zoneId: w.zoneId, reason: `Sin registro de hidratación hace ${since} min`, status: 'activa', createdAt: clock, peak: 0,
      });
    } else if (hyd && hState === 'overdue') {
      hyd.reason = `Sin registro de hidratación hace ${since} min`;
    } else if (hyd && hState !== 'overdue') {
      hyd.status = 'resuelta'; hyd.resolvedAt = clock; hyd.action = 'Hidratación registrada con el botón';
    }

    const open = alerts.find((a) => a.workerId === w.id && a.kind === 'salud' && a.status !== 'resuelta');
    if (w.status === 'normal') {
      if (open) { open.status = 'resuelta'; open.resolvedAt = clock; }
    } else if (!open) {
      alerts.unshift({
        id: nextAlertId++, kind: 'salud', level: w.status, workerId: w.id, workerName: w.name,
        zoneId: w.zoneId, reason: mainReason(w.factors), status: 'activa', createdAt: clock,
        peak: w.score,
      });
      if (w.status === 'alerta') newToasts.push({ level: 'alerta', text: `${w.name}: riesgo alto (${w.deviceId})` });
    } else {
      open.peak = Math.max(open.peak, w.score);
      if (open.level !== w.status) {
        if (w.status === 'alerta') newToasts.push({ level: 'alerta', text: `${w.name} escaló a riesgo alto` });
        open.level = w.status;
        open.reason = mainReason(w.factors);
      }
    }

    // Alertas de seguridad (acelerómetro: caída / sin movimiento)
    const sec = alerts.find((a) => a.workerId === w.id && a.kind === 'seguridad' && a.status !== 'resuelta');
    if (w.incident) {
      const fall = w.incident.type === 'caida';
      const critical = fall || w.stillMin >= th.stillMinutes * 2;
      const reason = fall ? 'Posible caída: impacto seguido de inmovilidad' : `Sin movimiento hace ${w.stillMin} min`;
      if ((fall || w.stillMin >= th.stillMinutes) && !sec) {
        alerts.unshift({
          id: nextAlertId++, kind: 'seguridad', level: critical ? 'alerta' : 'atencion', workerId: w.id, workerName: w.name,
          zoneId: w.zoneId, reason, status: 'activa', createdAt: clock, peak: 0,
        });
        if (critical) newToasts.push({ level: 'alerta', text: `${w.name}: ${fall ? 'posible caída' : 'sin movimiento'}` });
      } else if (sec) {
        if (!fall) sec.reason = reason;
        if (critical && sec.level !== 'alerta') {
          sec.level = 'alerta';
          newToasts.push({ level: 'alerta', text: `${w.name}: sin movimiento hace ${w.stillMin} min` });
        }
      }
    } else if (sec) { sec.status = 'resuelta'; sec.resolvedAt = clock; }

    // Alertas de dispositivo
    const dev = alerts.find((a) => a.workerId === w.id && a.kind === 'dispositivo' && a.status !== 'resuelta');
    const devIssue = !w.online ? 'Clip sin conexión' : w.battery < 15 ? `Batería baja (${Math.round(w.battery)}%)` : null;
    if (devIssue && !dev) {
      alerts.unshift({
        id: nextAlertId++, kind: 'dispositivo', level: 'atencion', workerId: w.id, workerName: w.name,
        zoneId: w.zoneId, reason: devIssue, status: 'activa', createdAt: clock, peak: 0,
      });
    } else if (!devIssue && dev) { dev.status = 'resuelta'; dev.resolvedAt = clock; }
  });

  alerts = alerts.slice(0, 200);
  workers = workers.slice();

  const next = { ...prev, clock, workers, alerts, events, nextAlertId };
  next.siteHistory = [...prev.siteHistory, buildSiteSnapshot(next, heatOffset)].slice(-HISTORY);
  return { state: next, toasts: newToasts };
}

// ─── Acciones del supervisor ────────────────────────────────────────────
export function orderPause(state, workerId, minutes = 15) {
  return {
    ...state,
    workers: state.workers.map((w) =>
      w.id === workerId
        ? { ...w, resting: true, restLeft: minutes, target: randomPointIn(REST_ZONE) }
        : w,
    ),
    alerts: state.alerts.map((a) =>
      a.workerId === workerId && a.kind === 'salud' && a.status === 'activa'
        ? { ...a, status: 'reconocida', ackAt: state.clock, action: `Pausa de ${minutes} min ordenada` }
        : a,
    ),
  };
}

// El supervisor envía un recordatorio al clip: vibra y el trabajador tiende a confirmar con el botón
export function hydrate(state, workerId) {
  return {
    ...state,
    workers: state.workers.map((w) => (w.id === workerId ? { ...w, reminderSent: true } : w)),
  };
}

// Pulsación del botón del clip (en el demo: simulada desde el panel)
export function registerDrink(state, workerId) {
  return {
    ...state,
    workers: state.workers.map((w) => (w.id === workerId
      ? { ...w, hydratedAt: state.clock, drinks: [...w.drinks, state.clock].slice(-12), drinkCount: w.drinkCount + 1, reminderSent: false }
      : w)),
    events: [{ type: 'hidratacion', clock: state.clock, workerId, workerName: state.workers.find((w) => w.id === workerId)?.name }, ...state.events].slice(0, 40),
    alerts: state.alerts.map((a) => (a.workerId === workerId && a.kind === 'hidratacion' && a.status !== 'resuelta'
      ? { ...a, status: 'resuelta', resolvedAt: state.clock, action: 'Hidratación registrada con el botón' }
      : a)),
  };
}

export function ackAlert(state, alertId) {
  return {
    ...state,
    alerts: state.alerts.map((a) => (a.id === alertId && a.status === 'activa' ? { ...a, status: 'reconocida', ackAt: state.clock } : a)),
  };
}

export function attendWorker(state, workerId) {
  return {
    ...state,
    workers: state.workers.map((w) => (w.id === workerId ? { ...w, incident: null, stillMin: 0, activity: 0.3 } : w)),
    alerts: state.alerts.map((a) =>
      a.workerId === workerId && a.kind === 'seguridad' && a.status !== 'resuelta'
        ? { ...a, status: 'resuelta', resolvedAt: state.clock, action: 'Atendido por supervisor' }
        : a,
    ),
  };
}

export function resolveAlert(state, alertId) {
  const target = state.alerts.find((a) => a.id === alertId);
  const attended = target && target.kind === 'seguridad';
  return {
    ...state,
    workers: attended
      ? state.workers.map((w) => (w.id === target.workerId ? { ...w, incident: null, stillMin: 0, activity: 0.3 } : w))
      : state.workers,
    alerts: state.alerts.map((a) => (a.id === alertId && a.status !== 'resuelta' ? { ...a, status: 'resuelta', resolvedAt: state.clock } : a)),
  };
}

export { SITE, ZONES };
