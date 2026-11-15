// Heat Index (HI) del National Weather Service (NWS), procedimiento completo:
// https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
// Mismo cálculo que src/lib/heatIndex.js del panel. No depende de Arduino, así que se puede
// compilar y probar en un computador (ver firmware/pruebas/test_heat_index.cpp).
//
// Indicador AUXILIAR: usa solo temperatura del aire y humedad relativa, representa condiciones de
// sombra y no incorpora la carga radiante. No es WBGT/TGBH (ISO 7243).
#pragma once
#include <math.h>

static inline float hgCtoF(float c) { return c * 9.0f / 5.0f + 32.0f; }
static inline float hgFtoC(float f) { return (f - 32.0f) * 5.0f / 9.0f; }

// T en °F, HR en %. Devuelve el Heat Index en °F.
static inline float hgHeatIndexF(float T, float RH) {
  if (RH < 0) RH = 0;
  if (RH > 100) RH = 100;
  // 1) Fórmula simple (Steadman), promediada con la temperatura
  float simple = 0.5f * (T + 61.0f + (T - 68.0f) * 1.2f + RH * 0.094f);
  float avg = (simple + T) / 2.0f;
  if (avg < 80.0f) return avg;
  // 2) Regresión de Rothfusz
  float hi = -42.379f + 2.04901523f * T + 10.14333127f * RH - 0.22475541f * T * RH
             - 0.00683783f * T * T - 0.05481717f * RH * RH + 0.00122874f * T * T * RH
             + 0.00085282f * T * RH * RH - 0.00000199f * T * T * RH * RH;
  // 3) Ajustes por humedad muy baja o muy alta
  if (RH < 13.0f && T >= 80.0f && T <= 112.0f) {
    hi -= ((13.0f - RH) / 4.0f) * sqrtf((17.0f - fabsf(T - 95.0f)) / 17.0f);
  } else if (RH > 85.0f && T >= 80.0f && T <= 87.0f) {
    hi += ((RH - 85.0f) / 10.0f) * ((87.0f - T) / 5.0f);
  }
  return hi;
}

// Entrada y salida en °C
static inline float hgHeatIndexC(float tC, float rh) { return hgFtoC(hgHeatIndexF(hgCtoF(tC), rh)); }

// Categoría del NWS: 0 normal (< 80 °F, sin categoría de precaución), 1 Precaución, 2 Precaución extrema (>= 90 °F),
// 3 Peligro (>= 103 °F), 4 Peligro extremo (>= 125 °F)
static inline int hgCategoria(float hiC) {
  float f = hgCtoF(hiC);
  if (f >= 125.0f) return 4;
  if (f >= 103.0f) return 3;
  if (f >= 90.0f) return 2;
  if (f >= 80.0f) return 1;
  return 0;
}

static inline const char *hgCategoriaNombre(int c) {
  static const char *n[] = {"normal", "Precaucion", "Precaucion extrema", "Peligro", "Peligro extremo"};
  return n[c < 0 ? 0 : c > 4 ? 4 : c];
}
