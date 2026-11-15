import test from 'node:test';
import assert from 'node:assert/strict';
import { decodeTelemetry, encodeTelemetry, validateTelemetry, lostBetween, encodeCommand, COMMAND, PACKET_BYTES, STATE, TELEMETRY_VERSION } from './telemetry.js';

const ejemplo = {
  seq: 513,
  env: { ok: true, tempC: 31.42, rhPct: 48.5, heatIndexC: 33.1 },
  motion: { ok: true, index: 37 },
  battery: { pct: 76, mV: 3960 },
  load: 104,
  state: STATE.descanso,
  pauses: 3,
  stateS: 1250,
  button: { pressed: false },
  requestBySupervisor: true,
  rssi: -63,
};

test('ida y vuelta del paquete de 20 bytes', () => {
  const view = encodeTelemetry(ejemplo);
  assert.equal(view.byteLength, PACKET_BYTES);
  const m = decodeTelemetry(view, { deviceId: 'HG-0101', receivedAt: 1000 });
  assert.equal(m.v, TELEMETRY_VERSION);
  assert.equal(m.deviceId, 'HG-0101');
  assert.equal(m.seq, 513);
  assert.ok(Math.abs(m.env.tempC - 31.42) < 0.006);
  assert.ok(Math.abs(m.env.rhPct - 48.5) < 0.006);
  assert.ok(Math.abs(m.env.heatIndexC - 33.1) < 0.006);
  assert.deepEqual(m.motion, { ok: true, index: 37 });
  assert.deepEqual(m.battery, { pct: 76, mV: 3960 });
  assert.equal(m.load, 104);
  assert.equal(m.state, STATE.descanso);
  assert.equal(m.pauses, 3);
  assert.equal(m.stateS, 1250);
  assert.equal(m.requestBySupervisor, true);
  assert.equal(m.rssi, -63);
  assert.equal(decodeTelemetry(encodeTelemetry({ ...ejemplo, rssi: null })).rssi, null, 'sin dato');
  assert.deepEqual(validateTelemetry(m), []);
});

test('sin sensor ambiental no hay temperatura, humedad ni Heat Index', () => {
  const m = decodeTelemetry(encodeTelemetry({ ...ejemplo, env: { ok: false } }));
  assert.deepEqual(m.env, { ok: false, tempC: null, rhPct: null, heatIndexC: null });
  assert.deepEqual(validateTelemetry(m), []);
});

test('temperaturas bajo cero y topes', () => {
  const m = decodeTelemetry(encodeTelemetry({ ...ejemplo, env: { ok: true, tempC: -3.25, rhPct: 80, heatIndexC: -3.25 }, stateS: 99999, load: 400 }));
  assert.ok(Math.abs(m.env.tempC + 3.25) < 0.006);
  assert.equal(m.stateS, 65535);
  assert.equal(m.load, 255);
});

test('rechaza paquetes cortos o de otra versión (por ejemplo, firmware v1)', () => {
  assert.throws(() => decodeTelemetry(new DataView(new ArrayBuffer(12))));
  const v = encodeTelemetry(ejemplo);
  v.setUint8(0, 1);
  assert.throws(() => decodeTelemetry(v), /Sube el firmware/);
});

test('la validación detecta valores fuera de rango', () => {
  const m = decodeTelemetry(encodeTelemetry(ejemplo));
  m.env.tempC = 150;
  m.state = 7;
  assert.equal(validateTelemetry(m).length, 2);
});

test('paquetes perdidos y comandos', () => {
  assert.equal(lostBetween(null, 5), 0);
  assert.equal(lostBetween(5, 6), 0);
  assert.equal(lostBetween(5, 9), 3);
  assert.equal(lostBetween(65535, 0), 0);
  assert.deepEqual([...encodeCommand(COMMAND.pauseRequest, 15)], [2, 15]);
  assert.deepEqual([...encodeCommand(COMMAND.cancelPauseRequest)], [6, 0]);
  assert.deepEqual([...encodeCommand(COMMAND.setLoadLimit, 120)], [7, 120]);
});
