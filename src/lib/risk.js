// Estado del trabajador según la EXPOSICIÓN ACUMULADA (calor + movimiento) y las pausas de hidratación y descanso.
//
// Idea del producto: el clip pide una pausa de hidratación y descanso cuando el trabajador lleva cierto
// tiempo expuesto al calor y moviéndose. La pausa empieza y termina solo cuando el trabajador mantiene
// presionado el botón del clip.
//
//   normal     verde parpadeante     condición óptima
//   cansancio  amarillo              la exposición llegó al umbral de cansancio
//   descanso   rojo + vibración      toca descanso: pausa solicitada (5 pulsos cada 40 s) hasta que se acepta
//   pausa      azul fijo             en pausa (botón mantenido 2 s)
//   finPausa   azul parpadeante + vibración   se cumplió el tiempo de pausa; se cierra con el botón
//
// La exposición acumulada es una REGLA DEL PROTOTIPO, sin validar: no es un índice normativo ni mide fatiga real.
// El mismo cálculo está en el firmware (firmware/heatguard_clip/heatguard_clip.ino).
import { hiCategory } from './heatIndex.js';

export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));

// Factor de calor por nivel (0 … 4). El nivel sale del WBGT estimado por el motor Python
// (motor_termico_python, modelo de Ono con meteorología Open-Meteo); si no hay WBGT, de la categoría del
// Heat Index del NWS como respaldo.
export const HEAT_FACTOR = [1, 1.5, 2, 3, 4];
export const heatFactor = (hiC) => HEAT_FACTOR[hiCategory(hiC)?.level ?? 0];

// Niveles de WBGT (°C) de la guía del Ministerio de Medio Ambiente de Japón (los mismos que
// motor_termico_python/integracion/servicio_wbgt.py). Regla del prototipo, sin validar en obra.
export const WBGT_LEVELS = [
  { level: 0, label: 'Casi seguro', minC: -Infinity, hex: '#16a34a' },
  { level: 1, label: 'Atención', minC: 21, hex: '#ca8a04' },
  { level: 2, label: 'Advertencia', minC: 25, hex: '#ea580c' },
  { level: 3, label: 'Advertencia severa', minC: 28, hex: '#dc2626' },
  { level: 4, label: 'Peligro', minC: 31, hex: '#7f1d1d' },
];
export const WBGT_REF_LINES = WBGT_LEVELS.slice(1, 4).map((l) => ({ value: l.minC, color: l.hex, label: `WBGT ${l.minC} °C` }));
export const hasWbgt = (w) => w?.wbgt != null && Number.isFinite(w.wbgt.c);
// Nivel de calor que usa la exposición: WBGT estimado si existe, si no sensación térmica
export function heatLevel(w) {
  if (hasWbgt(w)) {
    const lv = WBGT_LEVELS[Math.max(0, Math.min(4, w.wbgt.level))];
    return { source: 'wbgt', level: lv.level, label: lv.label, hex: lv.hex, valueC: w.wbgt.c };
  }
  const cat = hiCategory(w.env.hi);
  return { source: 'hi', level: cat?.level ?? 0, label: cat?.label ?? 'Normal', hex: cat?.hex, valueC: w.env.hi };
}
export const workerHeatFactor = (w) => HEAT_FACTOR[heatLevel(w).level];
// Factor de movimiento: quieto 0,75 · índice máximo 1,25
export const moveFactor = (mov01) => 0.75 + 0.5 * clamp(mov01);
// Factor personal según el índice de masa corporal (IMC = peso ÷ altura²). NIOSH menciona la obesidad como
// un factor que aumenta el riesgo por calor, pero no da un multiplicador: estos valores son una REGLA DEL
// PROTOTIPO, sin validar. Sin datos, el factor es ×1.
export const PERSONAL_FACTORS = [
  { maxBmi: 25, factor: 1.0, label: 'IMC bajo 25' },
  { maxBmi: 30, factor: 1.1, label: 'IMC 25 a 30' },
  { maxBmi: Infinity, factor: 1.2, label: 'IMC 30 o más' },
];
export function bmi(heightCm, weightKg) {
  if (!(heightCm >= 120 && heightCm <= 230 && weightKg >= 35 && weightKg <= 250)) return null;
  return weightKg / (heightCm / 100) ** 2;
}
export function personalFactor(heightCm, weightKg) {
  const b = bmi(heightCm, weightKg);
  if (b == null) return 1;
  return PERSONAL_FACTORS.find((p) => b < p.maxBmi).factor;
}

// Exposición que suma cada minuto, en % del límite
// level: nivel de calor (0–4) del WBGT estimado; null = usar la categoría del Heat Index
export const loadRate = (hiC, mov01, th, personal = 1, level = null) =>
  (100 * (level != null ? HEAT_FACTOR[level] : heatFactor(hiC)) * moveFactor(mov01) * personal) / th.loadLimit;
// Recuperación por minuto de pausa: una pausa completa devuelve la exposición de 100 % a 0 %
export const recoveryRate = (th) => 100 / th.pauseMinutes;
// Minutos de trabajo hasta el límite, con un factor de calor dado, movimiento medio y factor personal
export const minutesToLimit = (th, factor, personal = 1) => th.loadLimit / (factor * personal);

export const TIRED_HYSTERESIS = 5; // puntos de exposición bajo el umbral para volver de cansancio a normal

export const DEFAULT_THRESHOLDS = {
  loadLimit: 120,     // minutos-equivalentes de exposición para llegar a 100 % (120 min en sombra fresca, 40 min en "Peligro")
  tiredPct: 70,       // desde aquí: cansancio (amarillo)
  pauseMinutes: 15,   // duración de la pausa de hidratación y descanso
  autoPause: true,    // al llegar al 100 % se solicita la pausa sola
  confirmMinutes: 5,  // minutos de pausa solicitada sin aceptar antes de alertar al supervisor
  simResponds: true,  // los trabajadores simulados presionan el botón cuando el clip lo pide
};

// Estado del clip a partir de la exposición y la pausa. prev permite la histéresis del amarillo.
export function computeStatus({ load, resting, pauseElapsed, pauseReq }, th, prev = null) {
  if (resting) return pauseElapsed >= th.pauseMinutes ? 'finPausa' : 'pausa';
  if (pauseReq) return 'descanso';
  if (load >= th.tiredPct) return 'cansancio';
  if (prev === 'cansancio' && load > th.tiredPct - TIRED_HYSTERESIS) return 'cansancio';
  return 'normal';
}

export function mainReason(w) {
  if (w.pauseReq?.source === 'supervisor') return 'Pausa solicitada por el supervisor';
  const h = heatLevel(w);
  const f = HEAT_FACTOR[h.level];
  const fuente = h.source === 'wbgt' ? `WBGT estimado ${h.valueC.toFixed(1)} °C` : 'sensación térmica (Heat Index)';
  return `Exposición ${Math.round(w.load)} % · ${fuente} ${h.label.toLowerCase()} (×${f}) · movimiento ${Math.round(w.activity * 100)} (${w.activity < 0.34 ? 'bajo' : w.activity < 0.67 ? 'medio' : 'alto'})`;
}

// Colores y textos (los mismos que muestra el LED del clip)
export const STATUS = {
  normal:    { label: 'Óptimo',         hex: '#16a34a', led: 'verde parpadeante', badge: 'bg-green-50 text-green-700 border-green-200', dot: 'bg-green-500', bar: 'bg-green-500' },
  cansancio: { label: 'Cansancio',      hex: '#ca8a04', led: 'amarillo', badge: 'bg-yellow-50 text-yellow-800 border-yellow-300', dot: 'bg-yellow-500', bar: 'bg-yellow-500' },
  descanso:  { label: 'Toca descanso',  hex: '#dc2626', led: 'rojo + vibración', badge: 'bg-red-50 text-red-700 border-red-200', dot: 'bg-red-500', bar: 'bg-red-500' },
  pausa:     { label: 'En pausa',       hex: '#2563eb', led: 'azul fijo', badge: 'bg-blue-50 text-blue-700 border-blue-200', dot: 'bg-blue-500', bar: 'bg-blue-500' },
  finPausa:  { label: 'Pausa cumplida', hex: '#1d4ed8', led: 'azul parpadeante + vibración', badge: 'bg-indigo-50 text-indigo-700 border-indigo-300', dot: 'bg-indigo-500', bar: 'bg-indigo-500' },
  offline:   { label: 'Sin señal',      hex: '#64748b', led: '—', badge: 'bg-slate-100 text-slate-600 border-slate-200', dot: 'bg-slate-400', bar: 'bg-slate-400' },
};
export const WORK_STATES = ['normal', 'cansancio', 'descanso'];

// Estado "visible" (considera la conectividad)
export function displayStatus(w) {
  if (!w.online) return 'offline';
  return w.status;
}

export const STATUS_RANK = { descanso: 3, cansancio: 2, normal: 1, pausa: 0, finPausa: 0 };
