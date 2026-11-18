# Integración con el repositorio existente — contrato v2

## Fuentes revisadas (rama `main`, 17-11-2026)

- [`docs/contrato-datos.md`](https://github.com/R0RRO/heatguard-dashboard/blob/main/docs/contrato-datos.md): mensaje lógico **v2**; paquete BLE **20 bytes**, poco endian.
- [`src/lib/telemetry.js`](https://github.com/R0RRO/heatguard-dashboard/blob/main/src/lib/telemetry.js): decodificación y validación; servicio `7a1e0100-...`, característica `0101` (telemetría) y `0102` (comandos).
- [`firmware/heatguard_clip/heatguard_clip.ino`](https://github.com/R0RRO/heatguard-dashboard/blob/main/firmware/heatguard_clip/heatguard_clip.ino): firmware de producción del prototipo con control local de pausas por Heat Index/exposición, vibración y LED.
- [`server/index.js`](https://github.com/R0RRO/heatguard-dashboard/blob/main/server/index.js): servicio Node y rutas `/api/telemetry`, `/api/stream`, `/api/command` y `/api/state`.
- [`android/README.md`](https://github.com/R0RRO/heatguard-dashboard/blob/main/android/README.md): app móvil de relevo BLE -> Node en segundo plano.

El código Python v0.31 traía un receptor BLE basado en **otra variante de firmware** con características GATT `0004`/`0005`/`0006`/`0007`. **No es compatible automáticamente** con el contrato lógico BLE v2 actual. No sustituir el receptor o el firmware del equipo sin armonizarlo y probarlo con la placa.

## Separación de funciones que se debe conservar

| Origen / destino | Situación actual | Recomendación |
|---|---|---|
| Clip -> Android -> Node | Implementado por el compañero | No modificar ni duplicar |
| Clip calcula Heat Index, movimientos, estado y pausa | Implementado en el firmware actual; reglas no validadas | Conservar para demo, etiquetar correctamente |
| Node -> React, estado y comandos de pausa | Implementado | Seguir como fuente principal del dashboard |
| Node -> Python para WBGT experimental | **Implementado** (`integracion/servicio_wbgt.py`, 18-11-2026) | Puente local con clave; ver «Estado de la integración» |
| Python -> React, resultados estimación/rangos | **Implementado**: Node reenvía el WBGT estimado al panel y a la app | Etiquetado como «WBGT estimado (modelo Ono)» |
| Python -> actuadores BLE | **Decisión del equipo:** el nivel WBGT define el factor de calor; Node lo envía al clip (comando 11) | Una sola autoridad: el firmware sigue decidiendo el estado; el WBGT solo cambia su factor de calor |
| Sensor radiativo / viento local | Pendiente de hardware y calibración | Entradas opcionales con procedencia y modo degradado |

## Contrato mínimo de normalización

Usar `integracion/telemetry_v2_adapter.py` después de que Node o la aplicación haya **decodificado y validado** la telemetría. El adaptador recibe el mensaje JSON lógico v2 y devuelve el formato de observaciones `heatguard.pipeline.evaluate` o `POST /v1/fleet/ingest`.

Entrada abreviada:

```json
{
  "v": 2, "deviceId": "HeatGuard Clip", "receivedAt": 1794000000000,
  "seq": 513,
  "env": { "ok": true, "tempC": 31.42, "rhPct": 48.5, "heatIndexC": 33.1 },
  "motion": { "ok": true, "index": 37 },
  "battery": { "pct": 76, "mV": 3960 },
  "load": 104, "state": 2, "pauses": 3,
  "button": { "pressed": false }
}
```

Con T/H solamente el motor Python **no debe calcular WBGT completo**: faltan radiación y viento. Puede entregar Heat Index auxiliar, advertir insuficiencia y conservar procedencia. Si posteriormente se aportan radiación y viento externos con `source` y `timestamp`, el modelo evaluará si tiene entradas suficientes; no equiparar resultado a WBGT medido.

### Puntos que requieren decisión explícita

1. **Identificación:** definir dispositivo físico, `seq` reinicio, trabajador seudonimizado, zona de faena y horario exacto (UTC), sin duplicaciones.
2. **Seguridad:** compartir la telemetría normalizada mediante HTTP autenticado de servidor a servidor; nunca exponer una clave administrativa Python en Android o navegador.
3. **Titularidad:** Node conserva cuentas/sesiones/comandos; Python procesa ambiente y retorna un informe con `model_version`, `source_kind` y estado de validez.
4. **Frecuencia:** recortar/agrupaciones si manda cada dos segundos; no confundir muestra con minuto de exposición; tolerar desconexión y eventos tardíos.
5. **Contexto ocupacional:** trabajo pesado/descanso se declara separadamente; `motion.index` (0-100) NO es aceleración g ni esfuerzo metabólico ISO.
6. **Botón:** en firmware v2 la pulsación larga **comienza/termina pausa**, no representa automáticamente que bebió agua. Nunca registrar hidratación física solo por estar presionado.
7. **Actuadores:** decidir una fuente de verdad por estado/LED/motor. Conservar el control local de firmware para demo; cualquier nuevo semáforo WBGT experimental debe permanecer visual/supervisado hasta validar.
8. **Estados claros:** mostrar `Heat Index (NWS)` vs `WBGT estimado por modelo` vs `TGBH medido`, nunca mezclarlos.
9. **Control de versiones:** versionar contrato `v=2`; si se cambia el firmware, actualizar juntos Android, React, Node, adaptador y pruebas.

## Prueba de puente (sin hardware)

Ejecutar desde la raíz de esta carpeta:

```bash
python -m pytest -q tests/test_contract_v2_adapter.py
```

**No conectarse directamente a `/api/telemetry` desde Python sin evaluar identidad, permisos y carga de Node.** El motor Python no reemplaza ni implementa por sí mismo el puente de producción, y no existe un nuevo endpoint Node en esta entrega.

## Compatibilidad eléctrica actual

La unidad documentada utiliza `I²C SDA D4, SCL D8` (D5 dañado en ese ejemplar), RGB rojo D6, verde D3, azul D2; motor D7; botón D0. **El firmware y el cableado real del compañero son la fuente de verdad**, porque algunos documentos de versiones anteriores describen otro pinout. Evaluar consumos/encapsulado antes de añadir sensores.

## Estado de la integración (18-11-2026)

Decisión del equipo: el **WBGT estimado define las pausas** (reemplaza a la categoría del Heat Index en el
factor de calor de la exposición acumulada), para toda la cuadrilla, simulada y real.

- `integracion/servicio_wbgt.py`: servicio HTTP local (biblioteca estándar), `POST /v1/wbgt/lote` con clave
  `X-API-Key`. Usa `heatguard/weather.py` (Open-Meteo, radiación y viento regionales) y `heatguard/ono_v09.py`.
  Niveles WBGT (°C) del Ministerio de Medio Ambiente de Japón: <21, 21–25, 25–28, 28–31, ≥31 → factores ×1, ×1,5, ×2, ×3, ×4.
- `server/index.js` (Node): cada 1,5 s envía temperatura y humedad de cada trabajador (los simulados con la hora
  de su reloj simulado, los reales con la hora real) y aplica el resultado a la simulación.
- Clip real: Node manda el **comando 11** (nivel + 1) al celular del trabajador, que lo reenvía al clip. El firmware
  usa ese nivel por 10 min; si deja de llegar, vuelve a su Heat Index. Bandera 16 del paquete = factor por WBGT.
- Sin servicio o sin meteorología, todo vuelve a la sensación térmica (Heat Index) y el panel lo indica.
- Pruebas: `tests/test_servicio_wbgt.py`.

Sigue siendo una **estimación de modelo con meteorología regional**: no es WBGT/TGBH medido ni ISO 7243, y los
niveles y factores son una regla del prototipo sin validar en obra.
