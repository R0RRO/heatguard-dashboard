// Pruebas del modelo de carga, la simulación y la integración con un clip real.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createState, step, orderPause, cancelPause, pressButton } from './simulation.js';
import { DEFAULT_THRESHOLDS, computeStatus, loadRate, recoveryRate, heatFactor } from './risk.js';
import { heatIndexC } from './heatIndex.js';
import { decodeTelemetry, encodeTelemetry, STATE } from './telemetry.js';

const th = DEFAULT_THRESHOLDS;
const quietos = { ...th, simResponds: false };
const lectura = (extra = {}) => decodeTelemetry(encodeTelemetry({
  seq: 1, env: { ok: true, tempC: 34, rhPct: 55, heatIndexC: heatIndexC(34, 55) }, motion: { ok: true, index: 40 },
  battery: { pct: 64, mV: 3850 }, load: 40, state: STATE.normal, pauses: 0, stateS: 600, button: { pressed: false }, ...extra,
}));
const live = (msg, extra = {}) => ({ workerId: 'w1', msg, linked: true, dtMin: 0.03, ...extra });

test('modelo de carga: calor y movimiento suben la carga; la pausa la baja', () => {
  assert.equal(heatFactor(22), 1);
  assert.equal(heatFactor(heatIndexC(34, 55)), 3); // Peligro
  // 120 min en sombra fresca con movimiento medio llegan al 100 %
  assert.ok(Math.abs(loadRate(22, 0.5, th) * 120 - 100) < 1e-9);
  // con más calor llega antes
  assert.ok(loadRate(heatIndexC(34, 55), 0.5, th) > 2.9 * loadRate(22, 0.5, th));
  // una pausa completa devuelve 100 % a 0 %
  assert.equal(recoveryRate(th) * th.pauseMinutes, 100);
});

test('estados: óptimo, cansancio (con histéresis), toca descanso, en pausa, pausa cumplida', () => {
  const s = (o, prev) => computeStatus({ load: 0, resting: false, pauseElapsed: 0, pauseReq: null, ...o }, th, prev);
  assert.equal(s({ load: 50 }), 'normal');
  assert.equal(s({ load: 70 }), 'cansancio');
  assert.equal(s({ load: 67 }, 'cansancio'), 'cansancio');
  assert.equal(s({ load: 64 }, 'cansancio'), 'normal');
  assert.equal(s({ load: 20, pauseReq: { source: 'supervisor' } }), 'descanso');
  assert.equal(s({ resting: true, pauseElapsed: 3 }), 'pausa');
  assert.equal(s({ resting: true, pauseElapsed: 15 }), 'finPausa');
});

test('la simulación corre 300 minutos sin valores inválidos', () => {
  let s = createState(th, 0);
  for (let i = 0; i < 300; i++) s = step(s, th, 2).state;
  for (const w of s.workers) {
    assert.equal(w.source, 'sim');
    assert.ok(Number.isFinite(w.load) && w.load >= 0 && w.load <= 150);
    assert.ok(['normal', 'cansancio', 'descanso', 'pausa', 'finPausa'].includes(w.status));
    assert.ok(Math.abs(w.env.hi - heatIndexC(w.env.t, w.env.rh)) < 1e-9);
    assert.ok(w.history.every((p) => Number.isFinite(p.hi) && Number.isFinite(p.load)));
  }
  assert.ok(s.siteHistory.every((p) => Number.isFinite(p.hi)));
});

test('sin presionar el botón nadie entra en pausa: al 100 % solo se solicita', () => {
  let s = createState(quietos, 0);
  const enPausa = new Set(s.workers.filter((w) => w.resting).map((w) => w.id));
  for (let i = 0; i < 240; i++) s = step(s, quietos, 6).state;
  for (const w of s.workers) {
    if (!enPausa.has(w.id)) assert.equal(w.resting, false, `${w.name} entró en pausa solo`);
    if (w.load >= 100 && !w.resting) assert.equal(w.status, 'descanso');
  }
  assert.ok(s.workers.some((w) => w.pauseReq?.source === 'auto'));
  assert.ok(!s.events.some((e) => e.type === 'pausa-inicio'));
  assert.ok(s.alerts.some((a) => a.kind === 'descanso' && a.status === 'activa'));
});

test('ciclo completo: solicitud → botón → pausa → pausa cumplida → botón', () => {
  const t1 = { ...quietos, autoPause: false };
  let s = createState(t1, 0);
  s = orderPause(s, 'w2', 15);
  assert.equal(s.workers[1].status, 'descanso');
  assert.equal(s.workers[1].resting, false);

  s = pressButton(s, 'w2', t1);
  assert.equal(s.workers[1].status, 'pausa');
  assert.equal(s.events[0].type, 'pausa-inicio');
  const carga = s.workers[1].load;

  for (let i = 0; i < 14; i++) s = step(s, t1, 0).state;
  assert.equal(s.workers[1].status, 'pausa');
  assert.ok(s.workers[1].load < carga);
  s = step(s, t1, 0).state;
  assert.equal(s.workers[1].status, 'finPausa', 'al cumplir el tiempo pasa a pausa cumplida');
  for (let i = 0; i < 10; i++) s = step(s, t1, 0).state;
  assert.equal(s.workers[1].status, 'finPausa', 'la pausa no termina sola');
  assert.ok(s.alerts.some((a) => a.workerId === 'w2' && a.kind === 'pausa' && a.status === 'activa'));

  const antes = s.workers[1].pausesToday;
  s = pressButton(s, 'w2', t1);
  assert.equal(s.workers[1].resting, false);
  assert.equal(s.workers[1].status, 'normal');
  assert.equal(s.workers[1].pausesToday, antes + 1);
  assert.equal(s.events[0].type, 'pausa-fin');
});

test('el trabajador puede comenzar una pausa voluntaria con el botón', () => {
  let s = createState(quietos, 0);
  const w = s.workers.find((x) => !x.resting && !x.pauseReq);
  s = pressButton(s, w.id, quietos);
  assert.equal(s.workers.find((x) => x.id === w.id).status, 'pausa');
});

test('retirar la solicitud de pausa', () => {
  let s = orderPause(createState(quietos, 0), 'w3', 15);
  s = cancelPause(s, 'w3', quietos);
  assert.equal(s.workers[2].pauseReq, null);
  assert.notEqual(s.workers[2].status, 'descanso');
});

test('un clip real manda su carga y su estado; el panel solo los muestra', () => {
  let s = createState(quietos, 0);
  s = step(s, quietos, 0, live(lectura({ load: 72, state: STATE.cansancio }))).state;
  const w = s.workers[0];
  assert.equal(w.source, 'clip');
  assert.equal(w.load, 72);
  assert.equal(w.status, 'cansancio');
  assert.equal(w.env.t, 34);
  assert.equal(w.battery, 64);
  assert.equal(w.activity, 0.4);
  assert.equal(s.workers[1].source, 'sim');
});

test('el clip real informa la pausa: inicio y fin con el botón', () => {
  const ev = (s) => s.events.find((e) => e.workerId === 'w1')?.type;
  let s = createState(quietos, 0);
  const base = s.workers[0].pausesToday;
  s = step(s, quietos, 0, live(lectura({ load: 101, state: STATE.descanso, stateS: 30 }))).state;
  assert.equal(s.workers[0].status, 'descanso');
  assert.equal(s.workers[0].resting, false);
  s = step(s, quietos, 0, live(lectura({ load: 95, state: STATE.pausa, stateS: 60 }))).state;
  assert.equal(s.workers[0].resting, true);
  assert.equal(ev(s), 'pausa-inicio');
  s = step(s, quietos, 0, live(lectura({ load: 0, state: STATE.finPausa, stateS: 900 }))).state;
  assert.equal(s.workers[0].status, 'finPausa');
  s = step(s, quietos, 0, live(lectura({ load: 0, state: STATE.normal, pauses: 1, stateS: 5 }))).state;
  assert.equal(s.workers[0].resting, false);
  assert.equal(ev(s), 'pausa-fin');
  assert.equal(s.workers[0].pausesToday, base + 1);
});

test('sin enlace el clip real queda sin señal y se abre una alerta de dispositivo', () => {
  let s = createState(th, 0);
  s = step(s, th, 0, live(lectura())).state;
  s = step(s, th, 0, live(lectura(), { linked: false })).state;
  assert.equal(s.workers[0].online, false);
  assert.ok(s.alerts.some((a) => a.workerId === 'w1' && a.kind === 'dispositivo' && a.status === 'activa'));
});

test('sin sensor ambiental no se inventa temperatura y se avisa', () => {
  let s = createState(th, 0);
  const t0 = s.workers[0].env.t;
  s = step(s, th, 0, live(lectura({ env: { ok: false } }))).state;
  assert.equal(s.workers[0].env.ok, false);
  assert.equal(s.workers[0].env.t, t0);
  assert.ok(s.alerts.some((a) => a.workerId === 'w1' && a.reason.includes('Sensor')));
});

test('con clip real, la espera de una pausa pedida se mide en minutos reales', () => {
  let s = createState(quietos, 0);
  s = orderPause(s, 'w1', 15);
  for (let i = 0; i < 6; i++) s = step(s, quietos, 0, live(lectura({ state: STATE.descanso, requestBySupervisor: true }), { dtMin: 0.05 })).state;
  const w = s.workers[0];
  assert.equal(w.pauseReq.source, 'supervisor');
  assert.ok(s.clock - w.pauseReq.since <= 1, `espera ${s.clock - w.pauseReq.since} min en vez de ~0,3`);
});

test('factor personal por IMC: más peso para la misma altura acumula exposición más rápido', async () => {
  const { personalFactor, bmi, loadRate } = await import('./risk.js');
  assert.ok(Math.abs(bmi(175, 70) - 22.857) < 0.01);
  assert.equal(personalFactor(175, 70), 1);
  assert.equal(personalFactor(175, 85), 1.1);
  assert.equal(personalFactor(175, 100), 1.2);
  assert.equal(personalFactor(null, 80), 1, 'sin datos el factor es ×1');
  assert.equal(personalFactor(30, 80), 1, 'valores imposibles se ignoran');
  assert.ok(Math.abs(loadRate(22, 0.5, th, 1.2) / loadRate(22, 0.5, th, 1) - 1.2) < 1e-9);
});

test('cambiar altura y peso cambia el ritmo de la simulación', async () => {
  const { setProfile } = await import('./simulation.js');
  const t1 = { ...quietos, autoPause: false };
  let a = createState(t1, 0);
  a = setProfile(a, 'w1', { heightCm: 175, weightKg: 70 });
  let b = setProfile(a, 'w1', { heightCm: 175, weightKg: 110 });
  a = { ...a, workers: a.workers.map((w) => (w.id === 'w1' ? { ...w, resting: false, pauseReq: null, load: 0, incident: null, online: true } : w)) };
  b = { ...b, workers: b.workers.map((w) => (w.id === 'w1' ? { ...w, resting: false, pauseReq: null, load: 0, incident: null, online: true } : w)) };
  const orig = Math.random; Math.random = () => 0.5;
  try {
    for (let i = 0; i < 20; i++) { a = step(a, t1, 0).state; b = step(b, t1, 0).state; }
  } finally { Math.random = orig; }
  assert.ok(Math.abs(b.workers[0].load / a.workers[0].load - 1.2) < 0.01, `${b.workers[0].load} vs ${a.workers[0].load}`);
});

