// Heat Index (HI) del National Weather Service (NWS), procedimiento completo:
// https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
//
// Es un indicador AUXILIAR calculado solo con temperatura del aire y humedad relativa.
// Representa condiciones de sombra y viento leve: no incorpora la carga radiante del sol ni de
// maquinaria, y no reemplaza al WBGT / TGBH (ISO 7243), que requiere temperatura de globo y de
// bulbo húmedo natural.
//
// El mismo procedimiento está implementado en el firmware (firmware/heatguard_clip/heat_index.h).

export const cToF = (c) => (c * 9) / 5 + 32;
export const fToC = (f) => ((f - 32) * 5) / 9;

// Fórmula simple (Steadman) usada por el NWS como primer paso. T en °F, RH en %.
export function heatIndexSimpleF(T, RH) {
  return 0.5 * (T + 61.0 + (T - 68.0) * 1.2 + RH * 0.094);
}

// Regresión de Rothfusz. T en °F, RH en %.
export function rothfuszF(T, RH) {
  return (
    -42.379 + 2.04901523 * T + 10.14333127 * RH - 0.22475541 * T * RH
    - 0.00683783 * T * T - 0.05481717 * RH * RH + 0.00122874 * T * T * RH
    + 0.00085282 * T * RH * RH - 0.00000199 * T * T * RH * RH
  );
}

// Procedimiento del NWS: primero la fórmula simple promediada con la temperatura; si ese valor
// llega a 80 °F se aplica Rothfusz con sus dos ajustes (humedad muy baja o muy alta).
export function heatIndexF(T, RH) {
  const rh = Math.min(100, Math.max(0, RH));
  const avg = (heatIndexSimpleF(T, rh) + T) / 2;
  if (avg < 80) return avg;
  let hi = rothfuszF(T, rh);
  if (rh < 13 && T >= 80 && T <= 112) {
    hi -= ((13 - rh) / 4) * Math.sqrt((17 - Math.abs(T - 95)) / 17);
  } else if (rh > 85 && T >= 80 && T <= 87) {
    hi += ((rh - 85) / 10) * ((87 - T) / 5);
  }
  return hi;
}

// Versión en °C (entrada y salida). Devuelve null si falta algún dato.
export function heatIndexC(tC, rh) {
  if (!Number.isFinite(tC) || !Number.isFinite(rh)) return null;
  return fToC(heatIndexF(cToF(tC), rh));
}

// Categorías del NWS (umbrales en °F; el valor en °C es solo la conversión).
export const HI_CATEGORIES = [
  { id: 'ninguna', level: 0, minF: -Infinity, label: 'Normal', hex: '#16a34a', text: 'Bajo los 80 °F (27 °C): el NWS no asigna una categoría de precaución.' },
  { id: 'precaucion', level: 1, minF: 80, label: 'Precaución', hex: '#ca8a04', text: 'Posible fatiga con exposición y actividad prolongadas.' },
  { id: 'precaucion-extrema', level: 2, minF: 90, label: 'Precaución extrema', hex: '#ea580c', text: 'Posibles calambres, agotamiento o golpe de calor con exposición y actividad prolongadas.' },
  { id: 'peligro', level: 3, minF: 103, label: 'Peligro', hex: '#dc2626', text: 'Probables calambres o agotamiento; posible golpe de calor con exposición y actividad prolongadas.' },
  { id: 'peligro-extremo', level: 4, minF: 125, label: 'Peligro extremo', hex: '#7f1d1d', text: 'Golpe de calor muy probable.' },
].map((c) => ({ ...c, minC: Number.isFinite(c.minF) ? fToC(c.minF) : -Infinity }));

export function hiCategory(hiC) {
  if (!Number.isFinite(hiC)) return null;
  const f = cToF(hiC);
  let cat = HI_CATEGORIES[0];
  for (const c of HI_CATEGORIES) if (f >= c.minF) cat = c;
  return cat;
}

// Umbrales en °C para dibujar líneas de referencia en los gráficos
export const HI_REF_LINES = HI_CATEGORIES.filter((c) => c.level > 0 && c.level < 4)
  .map((c) => ({ value: c.minC, color: c.hex, label: `${c.label} (${Math.round(c.minC)} °C)` }));

// Límites de aplicación, para mostrar junto a la métrica
export const HI_NOTE = 'Heat Index del NWS: indicador auxiliar calculado con temperatura del aire y humedad. Vale para sombra y viento leve; al sol directo la sensación puede ser mayor. No es WBGT/TGBH ni un índice normativo.';
