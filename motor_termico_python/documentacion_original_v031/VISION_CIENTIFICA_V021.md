# Propuesta de arquitectura HeatGuard — Concepto a validar

## Diferenciación real, no eslogan

El objetivo no es un wearable que diga 'hace calor'. Es una **red de microclimas térmicos**, calibrada por referencias del prevencionista, capaz de reconocer cuándo no tiene evidencia suficiente, con una capa posterior de carga fisiológica y decisiones supervisadas.

### Capa A — Medición local

**Clip existente:** temperatura, humedad, acelerómetro, batería, BLE. Es indispensable validar las mediciones ambientales del HTU21D con el mismo encapsulado definitivo, considerando calor del cuerpo, autocalentamiento, ventilación y radiación. Exigir metadatos de procedencia, calidad, hora y versión del firmware. Ninguna de las estimaciones de esta investigación fue tomada por este clip.

**Adición experimental de radiación:** termistores sobre dos parches con absorción solar diferente —por ejemplo uno oscuro expuesto y uno protegido/referencia—. La diferencia térmica aporta información radiativa, pero también depende de viento, orientación, emisividad y conductividad del soporte. Debe calibrarse con piranómetro y referencia WBGT, no puede llamarse 'radiación medida' hasta demostrar metrología y equivalencia. Un luxómetro mide iluminancia visible, NO radiación solar total en W/m², salvo calibración específica limitada.

**Viento:** anemómetro de faena compartido y metadatos de proximidad; evitar suponer que el viento a 10 m es el que experimenta un trabajador rodeado de maquinaria. Si se usa velocidad del trabajador, la velocidad del aire relativa requiere dirección del viento y de movimiento, no solo magnitud GPS/IMU.

### Capa B — Estimador físico y estadístico

- Ono: línea base transparente para meteorología exterior (no WBGT instrumental normativo).
- Liljegren: balance energético de globo y bulbo húmedo natural cuando existen entradas suficientes; instrumentación/modelo no equiparables automáticamente a referencia japonesa psicrométrica.
- Kong–Huber: aproximación analítica de Liljegren; requiere fuentes adicionales de irradiancia reflejada y longwave o aproximaciones documentadas. No copiar sus fuentes GPL-3 a aplicación comercial sin asesoría sobre licencia.
- Para cada dato: measured / modeled / external / assumed, edad, coordenadas/área, confianza y trazabilidad.
- Si faltan viento/radiación/validación: estado `insufficient_inputs`, no inventar WBGT. Si se detecta cambio brusco o problema de montaje: `low_quality` y solicitud de revisión.
- Dos salidas distintas: `estimate_c` (central) e `uncertainty_indicators` (exploratorio; nunca un umbral de seguridad sin evidencia).

### Capa C — Referencia ambiental por zona térmica

Un instrumento WBGT apropiado puede calibrar una **zona térmica**, no toda la obra por supuesto. La v0.21 simuló un historial de siete días en una estación meteorológica, NO el traslado de esa calibración a trabajadores móviles.

Hipótesis futura: un sitio puede tener anclas para áreas de sombra, radiación directa, metal caliente, excavación, interiores y superficies reflejantes. Los clips indican su microambiente, sin afirmar equivalencia cuando la distancia o carga radiante cambien. Estrategia de ubicación de anclas y exploración de cobertura/errores es I+D por resolver.

### Capa D — Contexto ocupacional y térmico acumulado

**ISO 7933/PHS** combina aire, radiación, viento, vapor, tasa metabólica, ropa y tiempo para modelar carga térmica **promedio**, no diagnosticar el estado real de una persona. La actividad del MPU6050 no identifica por sí sola el costo energético de herramientas, carga estática o levantamiento de objetos. Preferir catálogo de tareas validado por ergonomía, duración, PPE y aclimatización declarada y consentida.

Separar siempre `WBGT_ambiental` (ambiente), `exposicion_ponderada` (ambientes y tiempos) y `strain_fisiologico` (solo con fuentes y consentimientos autorizados). No sintetizar una nota 0–100 de salud con pesos arbitrarios.

**Dato crucial de Chile:** DS 594 art. 97 requiere ponderación temporal de TGBH en áreas de trabajo/descanso, art. 98 metabolismo de tareas y art. 98 bis —añadido 2026— incorpora deberes ante altas temperaturas. La plataforma puede facilitar trazabilidad, pero NO reemplaza mediciones reglamentarias ni a prevencionistas.

### Capa E — Complemento fisiológico futuro, con consentimiento explícito

FC/HR, temperatura cutánea y movimientos pueden aportar información sobre carga fisiológica; **no equivalen a temperatura central medida ni constituyen diagnóstico**. La literatura de 2026 muestra variabilidad importante entre trabajadores y actividades. Nunca exigir salud personal para que opere un clip ambiental.

### Capa F — Lo que puede ser innovación defendible

La contribución propia sería un **sistema adaptable y auditable**: microclima local + ancla profesional + fusión física/ML con abstención cuando faltan condiciones + análisis de tiempo/tarea. La novedad legal o patentabilidad requiere estudio de anterioridad; existe al menos una publicación científica de 2026 llamada 'HeatGuard' para otro wearable.

## GATES: condiciones para avanzar

G1: demostrar precisión T/RH reales del clip junto a termohigrómetro de referencia, al sol, sombra, ventilado, cerca y lejos del cuerpo.
G2: instalar WBGT normalizado por zona representativa y comparar clips simultáneamente, no mezclar instrumentos, offsets ni cronologías.
G3: comprobar error por zona y fecha y subestimaciones peligrosas frente a TGBH medido conforme a protocolo.
G4: evaluar falsa alarma y confianza del usuario/supervisor, no solo MAE.
G5: introducir optimización ML por cuantiles solo después de disponer de anclas de varias obras, con pruebas ciegas de obra y fecha.

## Fuentes

- LeyChile [DS 594](https://www.bcn.cl/leychile/navegar?idNorma=167766)
- ISO [7243:2017](https://www.iso.org/standard/67188.html), [7933:2023](https://www.iso.org/standard/78240.html)
- [OSHA](https://www.osha.gov/heat-exposure/hazards)
- [Kong–Huber 2024](https://doi.org/10.1029/2024GH001068)
- [Estudio 2022 globos pequeños](https://www.sciencedirect.com/science/article/pii/S0360132322010113)
- [Estudio 2026 wearables HeatGuard](https://doi.org/10.3390/s26082556)
