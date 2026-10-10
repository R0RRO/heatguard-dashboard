// Modelo de riesgo térmico (demo). Reemplazar por el algoritmo real del clip
// cuando exista backend/firmware.

export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));

// Índice de calor interno (Steadman, viento ~1 m/s): combina temperatura y humedad
// medidas por el clip. En la UI solo se muestra la temperatura ambiente.
export function apparentTemp(t, rh) {
  const e = (rh / 100) * 6.105 * Math.exp((17.27 * t) / (237.7 + t));
  return t + 0.33 * e - 0.7 - 4.0;
}

export const DEFAULT_THRESHOLDS = {
  attention: 50, // score >= => Atención (azul)
  alert: 72,     // score >= => Riesgo alto (rojo)
  autoPause: true,
  stillMinutes: 8, // minutos sin movimiento (acelerómetro) para alertar
  hydrationMinutes: 30, // intervalo entre registros del botón de hidratación antes de recordar
};

export function riskScore({ at, exposure, activity }) {
  const thermal = clamp((at - 28) / 18);
  const expo = clamp(exposure / 150);
  // El puntaje solo usa lo que el clip mide (ambiente + movimiento). El botón de hidratación es un registro
  // autodeclarado y no lo modifica.
  const score = 100 * (0.5 * thermal + 0.3 * expo + 0.2 * activity);
  return { score, factors: { thermal, expo, activity } };
}

export function statusFromScore(score, th) {
  if (score >= th.alert) return 'alerta';
  if (score >= th.attention) return 'atencion';
  return 'normal';
}

export function mainReason(factors) {
  const list = [
    ['thermal', 'Temperatura ambiente alta'],
    ['expo', 'Exposición acumulada prolongada'],
    ['activity', 'Alta actividad física'],
  ];
  const w = { thermal: 0.5, expo: 0.3, activity: 0.2 };
  return list
    .map(([k, label]) => ({ label, v: factors[k] * w[k] }))
    .sort((a, b) => b.v - a.v)
    .slice(0, 2)
    .map((x) => x.label)
    .join(' + ');
}

// Config visual (semáforo del clip: verde / azul / rojo)
export const STATUS = {
  normal:   { label: 'Normal',     hex: '#16a34a', badge: 'bg-green-50 text-green-700 border-green-200', dot: 'bg-green-500', bar: 'bg-green-500' },
  atencion: { label: 'Atención',   hex: '#2563eb', badge: 'bg-blue-50 text-blue-700 border-blue-200',   dot: 'bg-blue-500',  bar: 'bg-blue-500' },
  alerta:   { label: 'Riesgo alto', hex: '#dc2626', badge: 'bg-red-50 text-red-700 border-red-200',     dot: 'bg-red-500',   bar: 'bg-red-500' },
  pausa:    { label: 'En pausa',   hex: '#0891b2', badge: 'bg-cyan-50 text-cyan-700 border-cyan-200',   dot: 'bg-cyan-500',  bar: 'bg-cyan-500' },
  offline:  { label: 'Sin señal',  hex: '#64748b', badge: 'bg-slate-100 text-slate-600 border-slate-200', dot: 'bg-slate-400', bar: 'bg-slate-400' },
};

// Estado "visible" (considera pausa y conectividad)
export function displayStatus(w) {
  if (!w.online) return 'offline';
  if (w.resting && w.status === 'normal') return 'pausa';
  return w.status;
}

export const STATUS_RANK = { alerta: 3, atencion: 2, normal: 1 };
