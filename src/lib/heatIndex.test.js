// Casos de prueba del Heat Index contra la tabla publicada por el NWS/NOAA
// (https://www.weather.gov/safety/heat-index). Correr con: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { heatIndexF, heatIndexC, hiCategory, cToF, fToC, rothfuszF } from './heatIndex.js';

// [T °F, HR %, HI °F de la tabla del NWS]
const TABLA_NWS = [
  [80, 40, 80], [80, 60, 82], [80, 80, 84],
  [84, 40, 83], [84, 60, 88], [84, 80, 94],
  [90, 40, 91], [90, 50, 95], [90, 60, 100], [90, 70, 106], [90, 80, 113], [90, 90, 122], [90, 100, 132],
  [96, 40, 101], [96, 50, 108], [96, 60, 116], [96, 65, 121], [96, 75, 132],
  [100, 40, 109], [100, 50, 118], [100, 60, 129],
  [104, 40, 119], [104, 50, 131],
  [110, 40, 136],
];

test('coincide con la tabla del NWS (±1 °F por redondeo)', () => {
  for (const [T, RH, esperado] of TABLA_NWS) {
    const hi = heatIndexF(T, RH);
    assert.ok(Math.abs(hi - esperado) <= 1.0, `T=${T} °F, HR=${RH} %: ${hi.toFixed(1)} (tabla ${esperado})`);
  }
});

test('con HR > 85 % y 80–87 °F la tabla impresa del NWS no incluye el ajuste del procedimiento', () => {
  // La tabla da 87 °F para 80 °F y 100 %: es Rothfusz sin ajuste. El procedimiento completo suma ~2 °F.
  assert.ok(Math.abs(rothfuszF(80, 100) - 87) <= 1.0);
  assert.ok(Math.abs(heatIndexF(80, 100) - 89.3) <= 0.1);
});

test('bajo 80 °F usa la fórmula simple promediada con la temperatura', () => {
  const hi = heatIndexF(70, 50);
  const simple = 0.5 * (70 + 61 + (70 - 68) * 1.2 + 50 * 0.094);
  assert.equal(hi, (simple + 70) / 2);
  assert.ok(Math.abs(hi - 70) < 2);
});

test('ajuste por humedad muy baja (HR < 13 %, 80–112 °F) resta al valor de Rothfusz', () => {
  const T = 95, RH = 10;
  const ajuste = ((13 - RH) / 4) * Math.sqrt((17 - Math.abs(T - 95)) / 17);
  assert.ok(Math.abs(heatIndexF(T, RH) - (rothfuszF(T, RH) - ajuste)) < 1e-9);
  assert.ok(heatIndexF(T, RH) < rothfuszF(T, RH));
});

test('ajuste por humedad muy alta (HR > 85 %, 80–87 °F) suma al valor de Rothfusz', () => {
  const T = 82, RH = 95;
  const ajuste = ((RH - 85) / 10) * ((87 - T) / 5);
  assert.ok(Math.abs(heatIndexF(T, RH) - (rothfuszF(T, RH) + ajuste)) < 1e-9);
});

test('es continuo y creciente con la temperatura y con la humedad en el rango de uso', () => {
  for (let rh = 20; rh <= 90; rh += 10) {
    let prev = -Infinity;
    for (let t = 20; t <= 45; t += 0.5) {
      const hi = heatIndexC(t, rh);
      assert.ok(hi >= prev - 0.35, `salto hacia abajo en ${t} °C, ${rh} %`);
      prev = hi;
    }
  }
  assert.ok(heatIndexC(35, 60) > heatIndexC(35, 40));
});

test('conversión y categorías', () => {
  assert.ok(Math.abs(fToC(cToF(31.5)) - 31.5) < 1e-9);
  assert.equal(hiCategory(heatIndexC(22, 50)).id, 'ninguna');
  assert.equal(hiCategory(fToC(85)).id, 'precaucion');
  assert.equal(hiCategory(fToC(95)).id, 'precaucion-extrema');
  assert.equal(hiCategory(fToC(110)).id, 'peligro');
  assert.equal(hiCategory(fToC(126)).id, 'peligro-extremo');
  assert.equal(hiCategory(null), null);
  assert.equal(heatIndexC(NaN, 50), null);
});
