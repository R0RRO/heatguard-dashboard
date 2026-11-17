# Contrato BLE y auditoría de firmware v0.31

## Fuente examinada

- Repositorio: `https://github.com/R0RRO/heatguard-dashboard`
- Archivo: `panel_pruebas/firmware/heatguard_demo/heatguard_demo.ino`
- Commit fijado: `242f17f7f4e5edc1ce1e1295b341361996b06a35`
- SHA-256 del archivo: `D37C189E6533883C69FE61A494A929CD875CF8494785816692FC2DC36F84A403`
- Nombre anunciado: `HeatGuard Clip`

La comprobación fue estática sobre el código fuente. No hubo clip físico conectado; propiedades GATT, temporización y comportamiento de radio deben confirmarse con el protocolo físico.

## Características implementadas

| Función | UUID | Formato | Uso en v0.31 |
|---|---|---|---|
| Temperatura | `00002a6e-0000-1000-8000-00805f9b34fb` | `int16 LE / 100`, 2 bytes | Notify; °C |
| Humedad | `00002a6f-0000-1000-8000-00805f9b34fb` | `uint16 LE / 100`, 2 bytes | Notify; %RH |
| Batería | `00002a19-0000-1000-8000-00805f9b34fb` | `uint8`, 1 byte | Notify; estimación firmware |
| IMU/pasos | `7a1e0004-4865-6174-4775-617264436c70` | `<IhhhH`, 12 bytes | pasos, yaw/pitch/roll ×0,1°, magnitud ×0,001 g |
| LED | `7a1e0005-4865-6174-4775-617264436c70` | R,G,B; 3 bytes | Escritura manual de banco |
| Motor | `7a1e0006-4865-6174-4775-617264436c70` | intensidad,duración; 2 bytes | Escritura manual; duración en décimas de segundo |
| Botón | `7a1e0007-4865-6174-4775-617264436c70` | `<BBH`, 4 bytes | pressed, event 0/1/2, contador uint16 |

El botón usa antirrebote de 30 ms. Una pulsación larga se reconoce a 1.000 ms, incrementa el contador y emite evento 2. En HeatGuard ese evento significa únicamente “la persona declaró una hidratación”; no prueba ingesta, volumen ni estado fisiológico.

## Integridad de eventos

`ButtonEventTracker` conserva por dispositivo el último contador, sesión de arranque y ciclo de wrap. La pasarela:

1. descarta la repetición exacta del contador;
2. reconoce `65535 → 0` como wrap;
3. trata una caída no compatible con wrap como reinicio del firmware;
4. informa saltos como `events_missed_before`;
5. produce identificadores deterministas para la deduplicación del backend;
6. persiste el estado en `gateway_device_state_v31`, por lo que reiniciar la pasarela no duplica el último evento.

La asociación se hace por `device_id` configurado en la pasarela. Para producción debe añadirse un registro controlado que vincule identidad BLE, número de activo y seudónimo del trabajador; el nombre anunciado por sí solo no es identidad suficiente.

## Reconexión y entrega

- Bleak vuelve a descubrir/conectar con retroceso hasta 30 s.
- Al reconectar se reinicia el ensamblador temporal para no emparejar T/RH de sesiones diferentes.
- La cola GATT tiene límite y cualquier desborde se informa por stderr.
- Telemetría y eventos entran primero en la outbox SQLite; red, 5xx y 429 se reintentan.
- 401/403 quedan visibles y pendientes para corregir la credencial.
- 4xx de forma/contenido quedan `rejected` para intervención, no en un bucle infinito.

## Actuadores

No existe ruta desde el estimador, la exposición o los estados de revisión hacia LED/motor. Sólo se escriben si el operador proporciona `--allow-manual-actuators` y un comando manual. Antes de usarlos con personas se requieren análisis de peligros, límites eléctricos, prueba de fallo atascado y procedimiento autorizado.

## Pines confirmados por firmware

- SDA: D4.
- SCL: D8.
- D5: no usar; el firmware documenta corto a GND en esa placa.

Estos pines tienen precedencia sobre diagramas históricos de este paquete.
