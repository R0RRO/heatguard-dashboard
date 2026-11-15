# Contrato de datos del HeatGuard Clip (versión 2)

Define el mensaje que entrega un clip, para que la interfaz no dependa de si los datos vienen de la
simulación o del hardware (paso 5 del plan del MVP, informe de la Entrega 2). Hoy el transporte es
Bluetooth LE; el mismo mensaje lógico sirve para una API o un WebSocket.

- Implementación en el panel: `src/lib/telemetry.js` (codificar, decodificar y validar) y `src/lib/clipLink.js` (conexión, cola de comandos y reconexión).
- Implementación en el clip: `firmware/heatguard_clip/heatguard_clip.ino` (`struct Telemetria`).
- Modelo de exposición acumulada y estados: `src/lib/risk.js` (panel y simulación) y la sección «Exposición y estado» del firmware.
- Pruebas: `npm test` (`src/lib/telemetry.test.js`, `src/lib/simulation.test.js`).

La versión 2 reemplaza a la 1: el panel rechaza paquetes v1 y pide subir el firmware nuevo.

## Idea del producto

El clip pide **pausas de hidratación y descanso** cuando el trabajador acumula cierto tiempo expuesto al
calor y moviéndose. Lo decide el propio clip, con o sin el panel conectado. La pausa empieza y termina
**solo** cuando el trabajador mantiene presionado el botón 2 s; el panel puede pedir una pausa, pero no
poner a nadie en pausa.

### Exposición acumulada

Cada minuto de trabajo suma `(100 % ÷ límite) × factor de calor × factor de movimiento × factor personal`:

| Categoría del Heat Index (NWS) | Factor de calor |
|---|---|
| Normal (< 27 °C) | ×1 |
| Precaución | ×1,5 |
| Precaución extrema | ×2 |
| Peligro | ×3 |
| Peligro extremo | ×4 |

El factor de movimiento va de ×0,75 (clip quieto) a ×1,25 (índice de movimiento 100). El factor personal
sale del índice de masa corporal (altura y peso del trabajador, editables en el panel): ×1 bajo 25, ×1,1 de
25 a 30 y ×1,2 desde 30; sin datos, ×1. Sin sensor
ambiental se usa ×1; sin acelerómetro, ×1. Durante la pausa la exposición acumulada baja hasta 0 % en la duración
configurada. Con los valores por defecto (límite 120 min-equivalentes) el 100 % llega en unos 2 h con Heat Index normal, 1 h en «Precaución extrema» y 40 min en «Peligro». Son **reglas del prototipo, sin
validar**: la exposición acumulada no mide fatiga ni deshidratación reales.

### Estados y señales del clip

| Estado (código) | Cuándo | LED de estado | Vibración |
|---|---|---|---|
| Óptimo (0) | exposición bajo el umbral de cansancio | verde parpadeante | — |
| Cansancio (1) | exposición ≥ umbral (70 %); vuelve a óptimo 5 puntos bajo él | amarillo | — |
| Toca descanso (2) | exposición ≥ 100 %, o el supervisor pide la pausa | rojo | 5 pulsos en ~2 s, cada 40 s |
| En pausa (3) | el trabajador mantuvo el botón 2 s | azul fijo | una al comenzar |
| Pausa cumplida (4) | pasó la duración de la pausa (15 min) | azul parpadeante | 3 pulsos largos cada 40 s |

### Botón

Hay que mantenerlo 2 s, para que no se active por accidente. Una pulsación corta no hace nada.

| Situación | Efecto de mantenerlo 2 s |
|---|---|
| En pausa o pausa cumplida | Termina la pausa (dos vibraciones). Cuenta una pausa completada. |
| Toca descanso | Comienza la pausa solicitada. |
| Óptimo o cansancio | Comienza una pausa voluntaria. |

## Mensaje lógico

```json
{
  "v": 2,
  "deviceId": "HeatGuard Clip",
  "receivedAt": 1794000000000,
  "seq": 513,
  "env": { "ok": true, "tempC": 31.42, "rhPct": 48.5, "heatIndexC": 33.1 },
  "motion": { "ok": true, "index": 37 },
  "battery": { "pct": 76, "mV": 3960 },
  "load": 104,
  "state": 2,
  "pauses": 3,
  "stateS": 1250,
  "button": { "pressed": false },
  "rssi": -63,
  "requestBySupervisor": false
}
```

| Campo | Unidad y rango | Significado |
|---|---|---|
| `v` | 2 | Versión del contrato. El panel rechaza otras versiones. |
| `seq` | 0–65535, cíclico | Número de secuencia; permite contar paquetes perdidos. |
| `env.ok` | booleano | El sensor de temperatura y humedad respondió. Si es falso, los tres valores van en `null`. |
| `env.tempC` / `env.rhPct` | °C / %, resolución 0,01 | Temperatura del aire y humedad relativa. |
| `env.heatIndexC` | °C | Heat Index del NWS calculado en el clip. Indicador auxiliar, no WBGT. |
| `motion.ok` / `motion.index` | booleano / 0–100 | Índice de movimiento: aceleración dinámica RMS en ~2 s (100 = 0,35 g). Sin validar. |
| `battery.pct` / `battery.mV` | %, mV | Estimación por voltaje con una curva típica de LiPo. |
| `load` | %, 0–150 | Exposición acumulada respecto del límite. Puede pasar de 100 mientras espera que comience la pausa. |
| `state` | 0–4 | Estado del clip (tabla de arriba). Lo decide el clip; el panel solo lo muestra. |
| `pauses` | 0–255 | Pausas completadas desde el encendido. |
| `stateS` | segundos, tope 65535 | En pausa: desde que comenzó. Si no: desde que terminó la última (o desde el encendido). |
| `button.pressed` | booleano | El botón está presionado en este momento. |
| `rssi` | dBm o `null` | Intensidad de la señal del enlace, medida por el clip cada 2 s (el navegador no puede leerla de un dispositivo conectado). |
| `requestBySupervisor` | booleano | La pausa pendiente la pidió el supervisor (si no, la pidió el clip al llegar al 100 %). |

El panel valida los rangos antes de usar una lectura (`validateTelemetry`) y descarta y cuenta las inválidas.

## Transporte Bluetooth LE

Nombre anunciado: `HeatGuard Clip`. Servicio `7a1e0100-4865-6174-4775-617264436c70`.

| Característica | UUID | Uso |
|---|---|---|
| Telemetría | `7a1e0101-…` | Notificación y lectura. Paquete de 20 bytes cada 2 s, y al instante tras el botón o un comando. |
| Comandos | `7a1e0102-…` | Escritura de 2 bytes: `[comando, argumento]`. El panel los envía en cola. |

Paquete de telemetría (little-endian, 20 bytes; cabe en una notificación sin negociar MTU):

| Byte | Tipo | Campo |
|---|---|---|
| 0 | uint8 | versión (2) |
| 1 | uint8 | banderas: bit 0 ambiente ok, bit 1 movimiento ok, bit 2 botón presionado, bit 3 pausa pedida por el supervisor |
| 2 | uint16 | secuencia |
| 4 | int16 | temperatura en centésimas de °C |
| 6 | uint16 | humedad en centésimas de % |
| 8 | int16 | Heat Index en centésimas de °C (−32768 = sin lectura) |
| 10 | uint8 | índice de movimiento |
| 11 | uint8 | batería en % |
| 12 | uint16 | batería en mV |
| 14 | uint8 | exposición acumulada en % |
| 15 | uint8 | estado (0–4) |
| 16 | uint8 | pausas completadas |
| 17 | int8 | intensidad de la señal Bluetooth del enlace en dBm, medida por el clip (0 = sin dato) |
| 18 | uint16 | segundos del estado de pausa (ver `stateS`) |

Comandos del panel al clip:

| Comando | Argumento | Efecto en el clip |
|---|---|---|
| 2 Solicitar pausa | minutos (informativo) | Pasa a «toca descanso». No pone al trabajador en pausa. |
| 4 Duración de la pausa | minutos (5–60) | Cambia cuánto dura la pausa. |
| 5 Ubicar | — | Parpadea en blanco y vibra tres veces. |
| 6 Retirar solicitud | — | Retira una pausa pedida por el supervisor que aún no comienza. |
| 7 Límite de exposición | minutos-equivalentes (30–250) | Cambia cuándo se llega al 100 %. |
| 8 Umbral de cansancio | % (30–95) | Cambia cuándo pasa a amarillo. |
| 9 Pausa automática | 1 sí / 0 no | Si el clip pide la pausa solo al llegar al 100 %. |
| 10 Factor personal | factor × 100 (50–200) | Factor del trabajador asignado (por ejemplo, 110 = ×1,1). Altura y peso no salen del panel. |

Al conectarse, y cada vez que cambia la configuración en la página «Pausas», el panel envía los
comandos 4, 7, 8 y 9; al conectarse, al asignar el clip y al editar al trabajador, el 10. El clip guarda
la configuración en su memoria y la conserva aunque se apague. Sin configuración previa usa sus valores
por defecto (120, 70 %, 15 min, sí, ×1).

## Reconexión

Si el enlace se cae, el clip vuelve a anunciarse y sigue funcionando solo; el panel reintenta (1, 2, 4, 8 y
luego cada 10 s). Si pasan 10 s sin paquetes, el panel fuerza la reconexión. Mientras no llegan lecturas
(más de 8 s), el trabajador asignado aparece «Sin señal» y se abre una alerta de dispositivo; el panel no
inventa valores.

## Frecuencias

| Dato | Frecuencia |
|---|---|
| Temperatura, humedad, Heat Index, batería y telemetría BLE | cada 2 s |
| Exposición acumulada y estado | cada 1 s |
| Acelerómetro (lectura interna) | 50 Hz; el índice resume ~2 s |
| Simulación del panel | 1 tick = 1 minuto simulado, cada 1,5 s reales |
