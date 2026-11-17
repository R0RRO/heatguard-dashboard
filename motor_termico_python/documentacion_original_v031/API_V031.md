# Referencia de API v0.31

Base local predeterminada: `http://127.0.0.1:8000`. Envíe `X-API-Key` en las rutas protegidas.

## Permisos

- `HG_ADMIN_API_KEY`: ingesta, eventos, demo y cálculos de escritura.
- `HG_VIEWER_API_KEY`: panel, consultas, historial y exportación.
- `HG_GATEWAY_API_KEY`: credencial que la pasarela coloca en el encabezado; normalmente corresponde a un secreto administrativo dedicado.
- Sin claves configuradas: modo de desarrollo local, no apto para red compartida.

Respuesta esperada: 401 si falta la clave, 403 si no es válida o no tiene permiso y 422 si el cuerpo no cumple el contrato.

## Rutas principales

| Método y ruta | Permiso | Función |
|---|---|---|
| `GET /health` | Público | Estado y versión |
| `POST /v1/fleet/ingest` | Admin | Ingesta, estimación y exposición |
| `POST /v1/live/ingest` | Admin | Alias para pasarela BLE |
| `POST /v1/fleet/device-events` | Admin | Evento discreto del botón |
| `GET /v1/fleet` | Visor | Resumen persistido |
| `GET /v1/fleet/devices/{id}` | Visor | Último estado |
| `GET /v1/fleet/devices/{id}/history` | Visor | Historial de telemetría |
| `GET /v1/fleet/devices/{id}/events` | Visor | Eventos discretos |
| `GET /v1/fleet/devices/{id}/export.csv` | Visor | Exportación de telemetría |
| `GET /v1/mvp/devices` | Visor | Datos integrados del panel |
| `POST /v1/mvp/demo` | Admin | Demo, sólo con `HG_ENABLE_DEMO=1` |
| `GET /mvp` | Público | HTML; sus datos siguen protegidos |

El esquema exacto de la instalación está en `/openapi.json` y `/docs`.

## Evento de hidratación autodeclarada

```json
{
  "event_id": "HG-001:button:b0:c0:n7:t2",
  "device_id": "HG-001",
  "timestamp": "2026-11-15T15:00:00+00:00",
  "event_type": "hydration_self_report",
  "source": "ble_gatt_button_0007",
  "self_reported": true,
  "physiological_measurement": false,
  "metadata": {"pressed": true, "event_code": 2, "counter": 7}
}
```

Tipos permitidos: `hydration_self_report`, `button_short_press` y `button_counter_reset`. Todos exigen `physiological_measurement=false`; una hidratación exige además `self_reported=true`.

## Reintentos de clientes

- Red, timeout, 429 y 5xx: reintento con retroceso e idempotencia.
- 401/403: conservar el evento, corregir la credencial y reanudar.
- 422 u otro 4xx de entrada: no reintentar sin corregir el evento.
- El cliente debe reutilizar `event_id`; la API responde `duplicate=true` sin crear otra fila.

El panel informa conectividad a partir de la edad de la última muestra. Ese campo no es una medición directa del enlace de radio.
