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

// Largo de paso promedio (m). Se podría calibrar por trabajador.
export const STRIDE_M = 0.7;

// Pasos y distancia estimada en los últimos N minutos (pasos × largo de paso)
export function recentSteps(history, minutes = 30) {
  return history.slice(-minutes).reduce((a, p) => a + (p.st || 0), 0);
}
export function distanceKm(history, minutes = 30) {
  return (recentSteps(history, minutes) * STRIDE_M) / 1000;
}

export const round1 = (n) => Math.round(n * 10) / 10;
