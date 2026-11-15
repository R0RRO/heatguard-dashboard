export function fmtClock(minutes) {
  const m = Math.floor(minutes) % 1440;
  const h = Math.floor(m / 60);
  return `${String(h).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

export function fmtDuration(min) {
  const m = Math.max(0, Math.round(min));
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

export const round1 = (n) => Math.round(n * 10) / 10;

// Niveles legibles para la interfaz
// Movimiento: índice 0–100 del acelerómetro (sin validar)
export function movLevel(index) {
  if (index == null || !Number.isFinite(index)) return '—';
  return index < 34 ? 'Bajo' : index < 67 ? 'Medio' : 'Alto';
}
// Señal Bluetooth medida por el clip (RSSI en dBm)
export function signalLevel(dbm) {
  if (dbm == null || !Number.isFinite(dbm)) return '—';
  return dbm >= -67 ? 'Alta' : dbm >= -80 ? 'Media' : 'Baja';
}
// Versión detallada para el supervisor: número y nivel
export const movDetail = (index) => (Number.isFinite(index) ? `${Math.round(index)} (${movLevel(index).toLowerCase()})` : '—');
export const signalDetail = (dbm) => (Number.isFinite(dbm) ? `${Math.round(dbm)} dBm (${signalLevel(dbm).toLowerCase()})` : '—');
