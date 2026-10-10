// Registro de hidratación con el botón del clip.
// Regla del demo: el clip recuerda (vibración + LED celeste) cuando pasan `hydrationMinutes` desde el último
// registro; el trabajador confirma con una pulsación larga. Es un dato AUTODECLARADO: el clip no mide hidratación.
// Si pasan 15 min más sin registro, el panel abre una alerta de hidratación.

export const DEFAULT_HYDRATION_MINUTES = 30;
export const OVERDUE_GRACE = 15;

export const sinceDrink = (w, clock) => Math.max(0, clock - w.hydratedAt);

// 'ok' | 'due' (el clip está recordando) | 'overdue' (sin registro tras el recordatorio)
export function hydrationState(w, clock, th) {
  const limit = th.hydrationMinutes ?? DEFAULT_HYDRATION_MINUTES;
  const since = sinceDrink(w, clock);
  if (since >= limit + OVERDUE_GRACE) return 'overdue';
  if (since >= limit) return 'due';
  return 'ok';
}

export const HYDRATION_LABEL = {
  ok: 'Al día',
  due: 'Recordatorio activo',
  overdue: 'Sin registro',
};

export const HYDRATION_BADGE = {
  ok: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  due: 'bg-blue-50 text-blue-700 border-blue-200',
  overdue: 'bg-amber-50 text-amber-800 border-amber-300',
};
