// Contrato de datos del HeatGuard Clip (versión 2). Documentado en docs/contrato-datos.md.
//
// Un mismo mensaje lógico describe una lectura del clip, sin importar el transporte (BLE hoy;
// API o WebSocket más adelante). La simulación y el clip real entregan esta misma forma, así la
// interfaz no depende del hardware.
//
// Por Bluetooth el mensaje viaja como un paquete binario de 20 bytes (little-endian), que cabe en
// una notificación BLE sin negociar MTU. El firmware que lo emite está en firmware/heatguard_clip.
//
// v2: el clip calcula la exposición acumulada (calor + movimiento) y decide su estado (óptimo, cansancio,
// toca descanso, en pausa, pausa cumplida). La pausa empieza y termina con el botón del clip.

export const TELEMETRY_VERSION = 2;
export const PACKET_BYTES = 20;

export const BLE = {
  name: 'HeatGuard Clip',
  service: '7a1e0100-4865-6174-4775-617264436c70',
  telemetry: '7a1e0101-4865-6174-4775-617264436c70', // notificación + lectura, paquete de 20 bytes
  command: '7a1e0102-4865-6174-4775-617264436c70',   // escritura: [comando, argumento]
};

// Comandos del panel hacia el clip
export const COMMAND = {
  pauseRequest: 2,       // el supervisor pide una pausa (argumento: minutos). El clip pasa a rojo y vibra hasta que se acepta con el botón
  setPauseMinutes: 4,    // duración de la pausa (argumento: minutos)
  identify: 5,           // parpadea y vibra para ubicar el clip
  cancelPauseRequest: 6, // retirar una solicitud de pausa que aún no se acepta
  setLoadLimit: 7,       // minutos-equivalentes para llegar al 100 % de exposición acumulada (argumento: 30–250)
  setTiredPct: 8,        // umbral de cansancio en % de exposición acumulada (argumento: 30–95)
  setAutoPause: 9,       // 1 = el clip pide la pausa solo al llegar al 100 %; 0 = no
  setPersonalFactor: 10, // factor personal del trabajador asignado × 100 (argumento: 50–200; 110 = ×1,1)
  setWbgtLevel: 11,      // nivel de WBGT estimado + 1 (1–5); 0 = el clip vuelve a su Heat Index
};
export const encodeCommand = (cmd, arg = 0) => new Uint8Array([cmd & 0xff, arg & 0xff]);

// Estados del clip (byte 15)
export const STATE = { normal: 0, cansancio: 1, descanso: 2, pausa: 3, finPausa: 4 };

const FLAG = { envOk: 1, motionOk: 2, buttonPressed: 4, requestBySupervisor: 8, heatFromWbgt: 16 };
const NO_VALUE = -32768; // int16 que marca "sin lectura"

// Paquete binario → mensaje lógico. Lanza un error si el paquete no es de esta versión.
export function decodeTelemetry(view, { deviceId = 'HG-CLIP', receivedAt = Date.now() } = {}) {
  if (!view || view.byteLength < PACKET_BYTES) throw new Error(`Paquete de ${view?.byteLength ?? 0} bytes (se esperaban ${PACKET_BYTES})`);
  const version = view.getUint8(0);
  if (version !== TELEMETRY_VERSION) throw new Error(`Versión de contrato ${version} no soportada (se esperaba ${TELEMETRY_VERSION}). Sube el firmware nuevo al clip.`);
  const flags = view.getUint8(1);
  const envOk = !!(flags & FLAG.envOk);
  const hiRaw = view.getInt16(8, true);
  return {
    v: version,
    deviceId,
    receivedAt,
    seq: view.getUint16(2, true),
    env: {
      ok: envOk,
      tempC: envOk ? view.getInt16(4, true) / 100 : null,
      rhPct: envOk ? view.getUint16(6, true) / 100 : null,
      heatIndexC: envOk && hiRaw !== NO_VALUE ? hiRaw / 100 : null,
    },
    motion: {
      ok: !!(flags & FLAG.motionOk),
      index: view.getUint8(10),      // 0–100, índice de movimiento (sin validar; no es tasa metabólica)
    },
    battery: { pct: view.getUint8(11), mV: view.getUint16(12, true) },
    load: view.getUint8(14),         // exposición acumulada en % del límite (puede pasar de 100 mientras espera la pausa)
    state: view.getUint8(15),        // ver STATE
    pauses: view.getUint8(16),       // pausas completadas desde el encendido
    stateS: view.getUint16(18, true), // en pausa: segundos desde que empezó; si no: desde la última pausa (o el encendido)
    rssi: view.getInt8(17) || null,  // intensidad de la señal del enlace medida por el clip (dBm); null = sin dato
    button: { pressed: !!(flags & FLAG.buttonPressed) },
    requestBySupervisor: !!(flags & FLAG.requestBySupervisor),
    heatFromWbgt: !!(flags & FLAG.heatFromWbgt),   // el clip usa el nivel WBGT del servidor como factor de calor
  };
}

// Mensaje lógico → paquete binario (lo usan las pruebas y un eventual emulador del clip)
export function encodeTelemetry(m) {
  const buf = new ArrayBuffer(PACKET_BYTES);
  const v = new DataView(buf);
  let flags = 0;
  if (m.env?.ok) flags |= FLAG.envOk;
  if (m.motion?.ok) flags |= FLAG.motionOk;
  if (m.button?.pressed) flags |= FLAG.buttonPressed;
  if (m.requestBySupervisor) flags |= FLAG.requestBySupervisor;
  if (m.heatFromWbgt) flags |= FLAG.heatFromWbgt;
  v.setUint8(0, TELEMETRY_VERSION);
  v.setUint8(1, flags);
  v.setUint16(2, (m.seq ?? 0) & 0xffff, true);
  v.setInt16(4, m.env?.ok ? Math.round(m.env.tempC * 100) : 0, true);
  v.setUint16(6, m.env?.ok ? Math.round(m.env.rhPct * 100) : 0, true);
  v.setInt16(8, m.env?.ok && m.env.heatIndexC != null ? Math.round(m.env.heatIndexC * 100) : NO_VALUE, true);
  v.setUint8(10, Math.round(m.motion?.index ?? 0));
  v.setUint8(11, Math.round(m.battery?.pct ?? 0));
  v.setUint16(12, Math.round(m.battery?.mV ?? 0), true);
  v.setUint8(14, Math.min(255, Math.round(m.load ?? 0)));
  v.setUint8(15, m.state ?? 0);
  v.setUint8(16, (m.pauses ?? 0) & 0xff);
  v.setInt8(17, Math.max(-127, Math.min(0, Math.round(m.rssi ?? 0)))); // RSSI en dBm (0 = sin dato)
  v.setUint16(18, Math.min(65535, Math.round(m.stateS ?? 0)), true);
  return v;
}

// Revisión de rangos antes de usar una lectura. Devuelve la lista de problemas (vacía si está bien).
export function validateTelemetry(m) {
  const e = [];
  const between = (x, a, b) => Number.isFinite(x) && x >= a && x <= b;
  if (m?.v !== TELEMETRY_VERSION) e.push('versión de contrato desconocida');
  if (!m?.env || !m?.motion || !m?.battery) { e.push('faltan campos'); return e; }
  if (m.env.ok) {
    if (!between(m.env.tempC, -20, 70)) e.push(`temperatura fuera de rango (${m.env.tempC} °C)`);
    if (!between(m.env.rhPct, 0, 100)) e.push(`humedad fuera de rango (${m.env.rhPct} %)`);
    if (m.env.heatIndexC != null && !between(m.env.heatIndexC, -20, 120)) e.push('Heat Index fuera de rango');
  }
  if (!between(m.motion.index, 0, 100)) e.push('índice de movimiento fuera de rango');
  if (!between(m.battery.pct, 0, 100)) e.push('batería fuera de rango');
  if (!between(m.load, 0, 255)) e.push('exposición fuera de rango');
  if (![0, 1, 2, 3, 4].includes(m.state)) e.push('estado desconocido');
  return e;
}

// Paquetes perdidos entre dos números de secuencia consecutivos (contador de 16 bits)
export const lostBetween = (prevSeq, seq) => (prevSeq == null ? 0 : Math.max(0, ((seq - prevSeq + 65536) % 65536) - 1));
