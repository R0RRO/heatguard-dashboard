// Prueba del Heat Index del firmware en un computador, contra la tabla del NWS.
//   cd firmware/pruebas && g++ -std=c++17 -o /tmp/test_hi test_heat_index.cpp && /tmp/test_hi
// Va fuera de la carpeta del programa para que arduino-cli no intente compilarlo.
#include <cstdio>
#include <cmath>
#include "../heatguard_clip/heat_index.h"

int main() {
  // T °F, HR %, HI °F de la tabla del NWS (https://www.weather.gov/safety/heat-index)
  const float tabla[][3] = {
    {80, 40, 80}, {80, 60, 82}, {80, 80, 84}, {84, 40, 83}, {84, 60, 88}, {84, 80, 94},
    {90, 40, 91}, {90, 50, 95}, {90, 60, 100}, {90, 70, 106}, {90, 80, 113}, {90, 90, 122}, {90, 100, 132},
    {96, 40, 101}, {96, 50, 108}, {96, 60, 116}, {96, 65, 121}, {96, 75, 132},
    {100, 40, 109}, {100, 50, 118}, {100, 60, 129}, {104, 40, 119}, {104, 50, 131}, {110, 40, 136},
  };
  int fallas = 0;
  for (auto &f : tabla) {
    float hi = hgHeatIndexF(f[0], f[1]);
    bool ok = fabsf(hi - f[2]) <= 1.0f;
    if (!ok) fallas++;
    printf("%s T=%3.0f F HR=%3.0f %%  HI=%6.1f F (tabla %3.0f)\n", ok ? "ok   " : "FALLA", f[0], f[1], hi, f[2]);
  }
  // Valores en °C para comparar con el panel (src/lib/heatIndex.js)
  const float casos[][2] = {{22, 50}, {28, 45}, {30, 60}, {34, 55}, {36.25f, 39}, {40, 34}, {33, 90}, {35, 10}};
  for (auto &c : casos) printf("C  T=%5.2f C HR=%3.0f %%  HI=%6.2f C  cat %d (%s)\n", c[0], c[1], hgHeatIndexC(c[0], c[1]), hgCategoria(hgHeatIndexC(c[0], c[1])), hgCategoriaNombre(hgCategoria(hgHeatIndexC(c[0], c[1]))));
  printf("%s\n", fallas ? "HAY FALLAS" : "Todo bien");
  return fallas ? 1 : 0;
}
