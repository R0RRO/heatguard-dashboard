# Protocolo mínimo de validación instrumental (para construir evidencia nueva)

**Objetivo:** demostrar precisión y sensibilidad del sistema instalado, no solo del modelo meteorológico retrospectivo.

## Instrumentos y escenarios

- Clip físico, carcasa final y configuración exacta de firmware.
- Termohigrómetro calibrado como referencia local; instrumento **WBGT/TGBH de referencia** apropiado, con certificados y calibración vigente.
- Radiación y viento instrumentales, si disponibles; cronómetros y registro de tareas/ropa.
- Condiciones: sombra, sol directo, zonas con calor radiante industrial, interiores, viento variable, diversas tareas; al menos varias zonas y jornadas.

## Procedimiento

1. Preparar consentimiento/anonimización y permisos de faena. Registrar versión de firmware, modelo Python, intervalo y configuración.
2. Sincronizar relojes. Colocar el clip y referencia cerca del puesto de trabajo, sin bloquear ventilación; registrar la diferencia entre altura/posición de equipos.
3. Registrar T/RH de ambos, lecturas WBGT de referencia, radiación/viento, zona, tarea, EPP, actividad y pausas; identificar faltantes y desconexiones.
4. Evitar fuga de entrenamiento: usar jornadas o faenas **completamente nuevas** para evaluación final. No seleccionar margen p90/p95 usando los datos reservados.
5. Reportar MAE/RMSE, sesgo, percentil 95 de error absoluto, sensibilidad y falsos negativos por criterio ocupacional, falsas alertas por jornada, cobertura de intervalos y latencia/éxito de entrega.
6. Comparar con baseline Ono y sin ML; exigir mejora significativa antes de habilitar cambios automáticos.
7. Consultar un profesional de seguridad ocupacional sobre qué acciones y mensajes deben activar los avisos. No basar política en 28°C universal.

## Tabla de registro sugerida

`timestamp_utc,site_pseudo,zone_id,device_id_pseudo,sensor_model,firmware_version,air_clip_c,rh_clip_pct,air_ref_c,rh_ref_pct,wbgt_ref_c,solar_w_m2,wind_ms,work_state,activity_class,ppe,acclimatized,alert_state,delivery_status,quality_notes`

**Privacidad:** no publicar nombre, posición GPS individual, expediente de salud ni fotografías identificables sin autorización. Las métricas que vayan al pitch deben usar datos agregados.

## Criterios de aceptación

Deben fijarse **antes** del estudio con un profesional de prevención y con base en uso previsto: error medio aceptable, tasa máxima de falsos negativos por condición y tasa máxima de falsas alertas por jornada. Sin esto, reportar investigación y no declarar garantías de producto.
