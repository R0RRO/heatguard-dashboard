# Matriz de funcionalidades v0.31

Estados: **validado SW**, **implementado/no físico**, **pendiente** y **fuera de alcance**.

| Área | Estado | Evidencia v0.31 | Pendiente antes de piloto |
|---|---|---|---|
| API autenticada | validado SW | 401/403 y roles en pruebas | TLS, rotación, proxy y operación de producción |
| Gateway → API → DB | validado SW | integración con transporte HTTP y SQLite | prueba sobre red y gateway reales |
| Outbox/reintento | validado SW | red, auth, rechazo, dedup y reinicio | ensayo de corte eléctrico y disco lleno |
| BLE temperatura 2A6E | implementado/no físico | decodificación de bytes | sensor y radio reales |
| BLE humedad 2A6F | implementado/no físico | decodificación de bytes | sensor y radio reales |
| BLE batería 2A19 | implementado/no físico | rango y panel | curva/calibración/autonomía |
| BLE IMU 0004 | implementado/no físico | `<IhhhH` y panel | pasos, deriva y orientación reales |
| Botón 0007 | validado SW | largo/corto/dedup/wrap/reset | rebote, reinicio y uso físico |
| Hidratación | validado SW | evento autodeclarado persistente | validación de interfaz; nunca fisiología |
| LED 0005 | implementado/no físico | codificador RGB | límites eléctricos y banco seguro |
| Motor 0006 | implementado/no físico | intensidad/duración | límites, consumo y fallo atascado |
| Actuación automática | fuera de alcance | no existe ruta desde reglas | análisis de peligros y autorización explícita |
| Trabajo/descanso | validado SW | regresión heavy+rest y aceptación | protocolo humano/turnos en campo |
| Huecos y tardíos | validado SW | desconocido, orden y no rebobinado | prueba de red prolongada |
| Reinicio sin duplicados | validado SW | telemetría, eventos y contador | corte abrupto de energía |
| Ono exterior | validado SW | regresiones y reproducción | comparación local trazable |
| Liljegren opcional | validado SW | regresiones | entradas instrumentales completas |
| ML universal | fuera de alcance | peor extrapolación espacial | nuevos sitios y calibración local |
| Radiación meteorológica | validado SW | procedencia/edad | representatividad del puesto |
| Radiación instrumental | validado SW | ID/calibración/incertidumbre | integración con equipo real |
| Radiación manual | validado SW | marcada `assumed` | procedimiento y control de errores |
| Sensor diferencial | pendiente | modelo de datos y pines | diseño, montaje y calibración |
| Panel multi-clip | validado SW | seis clips en navegador | usabilidad con supervisores y carga prolongada |
| Exportación/historial | validado SW | suite API existente | retención y gobernanza de datos |
| Windows limpio | validado SW | instalación/extracción de liberación | instalador firmado, si se requiere |
| Linux/ZIP | validado estructural | rutas POSIX y extracción estándar | prueba BLE en distribución objetivo |
| ISO 7243 | fuera de alcance | aviso explícito | instrumento/procedimiento conforme |
| Uso médico | fuera de alcance | sin inferencia fisiológica | no está previsto |

“Validado SW” no significa validado físicamente ni aprobado para decisiones de seguridad.
