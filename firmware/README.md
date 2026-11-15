# Firmware del HeatGuard Clip

`heatguard_clip/` es el programa de la XIAO ESP32-C3 del prototipo. Calcula el Heat Index del NWS (indicador
auxiliar) y un índice de movimiento, acumula la exposición al calor y al movimiento, pide pausas de hidratación
y descanso con LED y vibración, y envía todo por Bluetooth con el contrato de datos v2
(`docs/contrato-datos.md`).

## Subirlo a la placa

Con la XIAO conectada por USB y el interruptor del clip apagado:

```bash
./panel_pruebas/subir_xiao.sh            # compila y sube firmware/heatguard_clip
```

El script instala `arduino-cli` y el soporte para ESP32 la primera vez, sube el programa y muestra 15 s
del puerto serie. Al encender, deja el clip quieto 2 segundos (calibra el giroscopio).

## Archivos

| Archivo | Contenido |
|---|---|
| `heatguard_clip/heatguard_clip.ino` | Programa principal. |
| `heatguard_clip/heat_index.h` | Heat Index del NWS (mismo cálculo que `src/lib/heatIndex.js`). No depende de Arduino. |
| `pruebas/test_heat_index.cpp` | Prueba del Heat Index en un computador contra la tabla del NWS. |

Probar el Heat Index sin la placa:

```bash
cd firmware/pruebas
g++ -std=c++17 -o /tmp/test_hi test_heat_index.cpp && /tmp/test_hi
```

## Comportamiento

El clip pide **pausas de hidratación y descanso** según la exposición acumulada (calor + movimiento) y decide
solo, con o sin el panel. La pausa empieza y termina únicamente con el botón mantenido 2 s. El detalle
está en `docs/contrato-datos.md`.

- **Al encender:** el LED de estado pasa por rojo, verde y azul; el LED de batería muestra el nivel 3 s
  (0–20 % rojo parpadeante, 20–50 % rojo, 50–80 % azul parpadeante, 80 % o más azul); una vibración corta.
- **Óptimo:** verde parpadeante.
- **Cansancio:** amarillo, desde 70 % de exposición.
- **Toca descanso:** rojo y 5 vibraciones cada 40 s, al llegar al 100 % o si el supervisor pide la pausa.
- **En pausa:** azul fijo, tras mantener el botón 2 s. La exposición acumulada baja mientras dura.
- **Pausa cumplida:** azul parpadeante y 3 vibraciones largas cada 40 s, hasta mantener el botón 2 s.
- **Botón:** una pulsación corta no hace nada. Mantenido 2 s comienza la pausa (pedida o voluntaria) o la
  termina si ya está en pausa.
- **Configuración:** límite, umbral de cansancio, duración de la pausa, pausa automática y factor personal
  los envía el panel; el clip los guarda en su memoria y los conserva aunque se apague.
- **Sin sensores:** si el sensor de temperatura o el acelerómetro no responden, el clip sigue funcionando
  con factor ×1, lo informa en la telemetría y reintenta.

Los factores, el límite, el índice de movimiento y el porcentaje de batería son reglas del prototipo sin
validar. El clip no tiene certificación ISO, no entrega diagnóstico médico y no predice golpes de calor.

## Pines de este prototipo

| Función | Pin |
|---|---|
| I2C SDA / SCL | D4 / D8 (D5 quedó en corto con GND y no se usa) |
| LED de estado RGB (cátodo común) | rojo D6, verde D3, azul D2 |
| LED de batería | rojo D9, azul D10 |
| Motor de vibración (1 kΩ → 2N2222) | D7 |
| Botón de pausa (a GND) | D0 |
| Divisor de batería | D1 |

El firmware es compatible con el panel de pruebas (`panel_pruebas/demo_ble`): al mandar un color o
una vibración desde ahí, el clip deja de controlar el LED y el motor por 20 s.
