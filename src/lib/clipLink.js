// Conexión con un clip real por Web Bluetooth (Chrome, Chromium o Edge; requiere https o localhost).
// Entrega cada paquete del contrato de datos ya decodificado y se reconecta sola si el enlace se cae.
import { BLE, decodeTelemetry, validateTelemetry, encodeCommand, lostBetween } from './telemetry.js';

const STALE_MS = 10000; // sin paquetes durante este tiempo: se fuerza la reconexión

export const bluetoothSupported = () => typeof navigator !== 'undefined' && !!navigator.bluetooth;

// onMessage(msg) recibe lecturas válidas; onStatus({ status, deviceName, error, lost, invalid }) los cambios de estado.
// status: 'off' | 'connecting' | 'connected' | 'reconnecting'
export function createClipLink({ onMessage, onStatus }) {
  let device = null;
  let cmdChar = null;
  let manual = false;
  let reconnecting = false;
  let lastSeq = null;
  let lastAt = 0;
  let watchdog = null;
  let queue = Promise.resolve();
  const stats = { lost: 0, invalid: 0 };

  const emit = (status, extra = {}) => onStatus?.({ status, deviceName: device?.name || null, error: null, ...stats, ...extra });

  const onPacket = (e) => {
    try {
      const msg = decodeTelemetry(e.target.value, { deviceId: device?.name || BLE.name, receivedAt: Date.now() });
      const problems = validateTelemetry(msg);
      if (problems.length) { stats.invalid += 1; emit('connected', { error: `Lectura descartada: ${problems.join(', ')}` }); return; }
      stats.lost += lostBetween(lastSeq, msg.seq);
      lastSeq = msg.seq;
      lastAt = Date.now();
      onMessage?.(msg);
    } catch (err) {
      stats.invalid += 1;
      emit('connected', { error: err.message });
    }
  };

  async function open() {
    const server = await device.gatt.connect();
    const service = await server.getPrimaryService(BLE.service);
    const tele = await service.getCharacteristic(BLE.telemetry);
    cmdChar = await service.getCharacteristic(BLE.command).catch(() => null);
    tele.addEventListener('characteristicvaluechanged', onPacket);
    await tele.startNotifications();
    lastSeq = null;
    lastAt = Date.now();
    emit('connected');
  }

  async function reconnect() {
    if (reconnecting || manual || !device) return;
    reconnecting = true;
    cmdChar = null;
    for (let i = 0; !manual; i++) {
      emit('reconnecting');
      await new Promise((r) => setTimeout(r, Math.min(10000, 1000 * 2 ** Math.min(i, 4))));
      if (manual) break;
      try { await open(); break; } catch { /* se reintenta */ }
    }
    reconnecting = false;
  }

  function startWatchdog() {
    clearInterval(watchdog);
    watchdog = setInterval(() => {
      if (manual || reconnecting || !device?.gatt.connected) return;
      if (Date.now() - lastAt > STALE_MS) device.gatt.disconnect(); // dispara gattserverdisconnected → reconnect()
    }, 2000);
  }

  return {
    async connect() {
      if (!bluetoothSupported()) throw new Error('Este navegador no tiene Bluetooth web. Usa Chrome, Chromium o Edge.');
      manual = false;
      emit('connecting');
      try {
        device = await navigator.bluetooth.requestDevice({ filters: [{ name: BLE.name }], optionalServices: [BLE.service] });
        device.addEventListener('gattserverdisconnected', reconnect);
        let error = null;
        for (let i = 0; i < 3; i++) { // en Linux el primer intento suele fallar
          try { await open(); error = null; break; } catch (err) { error = err; await new Promise((r) => setTimeout(r, 1500)); }
        }
        if (error) throw error;
        startWatchdog();
      } catch (err) {
        manual = true;
        clearInterval(watchdog);
        if (device?.gatt.connected) device.gatt.disconnect();
        device = null;
        const cancelled = err.name === 'NotFoundError';
        emit('off', { error: cancelled ? null : `No se pudo conectar: ${err.message}. ¿Tiene cargado el firmware heatguard_clip actualizado y está libre (sin otra app conectada)?` });
        if (!cancelled) throw err;
      }
    },
    disconnect() {
      manual = true;
      clearInterval(watchdog);
      if (device?.gatt.connected) device.gatt.disconnect();
      device = null;
      cmdChar = null;
      emit('off');
    },
    // Envía un comando al clip; devuelve false si no hay enlace. Los envíos van en cola, porque Web
    // Bluetooth rechaza una escritura mientras otra está en curso.
    send(cmd, arg = 0) {
      const run = async () => {
        if (!cmdChar || !device?.gatt.connected) return false;
        try { await cmdChar.writeValue(encodeCommand(cmd, arg)); return true; } catch { return false; }
      };
      queue = queue.then(run, run);
      return queue;
    },
    get connected() { return !!device?.gatt.connected && !reconnecting; },
  };
}
