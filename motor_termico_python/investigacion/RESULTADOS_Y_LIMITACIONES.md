# Investigación térmica — resumen verificable, no certificación

## Problema de medición

ISO 7243 evalúa estrés térmico mediante WBGT/TGBH; la medición requiere características ambientales que el clip actual **no mide directamente**: entre otras, radiación y viento a altura de trabajo. La temperatura/humedad del clip permiten calcular **Heat Index** como indicador auxiliar, pero no TGBH normativo.

Modelos examinados: **Ono (2014)** con T/RH, radiación y viento; **Liljegren et al. (2008)** como balance físico; **Kong & Huber (2024)** como alternativa analítica al balance; ML residual y cuantiles con controles de generalización. La calibración por faena/área térmica es una hipótesis prioritaria, no un procedimiento validado en obra.

## Resultados de investigación histórica

Con datos meteorológicos del **22–31 agosto de 2025** de Tokio, Osaka, Fukuoka y Sapporo (**960 horas**, 240 por estación) y referencia japonesa **parcialmente instrumental**, Ono obtuvo **MAE 0,771 °C** y **RMSE 1,003 °C**. **No son mediciones de HeatGuard Clip** y las fechas ya habían sido estudiadas previamente: no prueba ciega prospectiva.

Un corte **experimental**, **28 °C** WBGT de la referencia, fue utilizado únicamente para evaluar clasificación: **291/960** registros estaban por encima del corte.

| Regla exploratoria | Detectadas (sobre 291) | No detectadas | Falsas alertas |
|---|---:|---:|---:|
| Ono sin margen | 261 (89,7%) | 30 | 28 |
| Ono +1 °C fijo | 284 (97,6%) | 7 | 100 |
| Ono + margen p90 calibrado con 7 días por estación | 289 (99,3%) | 2 | 117 |
| Ono + margen p95 calibrado con 7 días por estación | 291 (100% observado) | 0 | 177 |

Los márgenes p90 fueron aproximadamente **0,47 °C Osaka, 1,04 °C Tokio, 1,36 °C Sapporo, 2,05 °C Fukuoka**. Cambian significativamente por zona. El margen **modifica la decisión**, no la precisión del sensor/estimador. Los resultados tienen falsas alertas y podrían no transferirse a zonas industriales, interiores, equipos radiativos, ropa o movimiento.

En experimentos anteriores, modelos ML universales fallaron al generalizar a ciudad excluida. Por eso **no se debe activar automáticamente un ML no validado** como controlador de seguridad.

## Cómo interpretar las 'garantías'

Se puede comunicar: "En evaluación retrospectiva meteorológica de cuatro estaciones, el clasificador experimental con calibración p90 detectó 289 de 291 casos por encima del corte investigado, con 117 falsas alertas." No se puede afirmar: "El clip es 99,3% efectivo", "99,3% de golpes de calor evitados", "±0,77 °C en terreno" o "certificado ISO".

## Rangos de HeatGuard (propuesta por validar)

ISO 7243 **no establece colores universales**. Los colores del producto pueden codificar **sin criterio de revisión disparado**, **revisión preventiva**, **revisión prioritaria** y **datos insuficientes**, siempre teniendo en cuenta trabajo metabólico, aclimatización, ropa/EPP, régimen trabajo-descanso, tiempo y calidad de información. Los criterios del DS 594 chileno no son un único umbral 28 °C. El estado verde nunca garantiza seguridad.

## Mejoras futuras a demostrar

1. T/RH real del HTU21D/AHTx montado en la carcasa, contra patrón calibrado.
2. Anclas TGBH instrumentales por zona térmica y sol/sombra; sincronización horaria.
3. Radiación/viento local medidos o estimados con procedencia explícita; estudiar sensor diferencial.
4. Evaluación con sitios y fechas nuevas; sensibilidad por carga de trabajo, tasa de falsos avisos por jornada, cobertura de incertidumbre y fiabilidad de entrega BLE.
5. Curva de precisión frente a costo de nuevos sensores; no agregar componentes sin demostrar beneficio incremental.

## Fuentes trazables

- [Ono et al. (2014) - ecuación meteorológica WBGT](https://www.jstage.jst.go.jp/article/seikisho/50/4/50_147/_article)
- [Liljegren et al. (2008)](https://pubmed.ncbi.nlm.nih.gov/18668404/)
- [Kong & Huber (2024)](https://doi.org/10.1029/2024GH001068)
- [ISO 7243:2017 - ficha oficial](https://www.iso.org/standard/67188.html)
- [DS 594, artículos 96–98 y otras disposiciones - BCN Chile](https://www.bcn.cl/leychile/navegar?idNorma=167766)
- [OSHA - evaluación de estrés térmico](https://www.osha.gov/heat-exposure/hazards)
- [CDC/NIOSH - recomendaciones de prevención](https://www.cdc.gov/niosh/heat-stress/recommendations/)

**Nota de redistribución:** los datasets JMA/Open-Meteo originales y modelos `.joblib` quedan fuera de esta carpeta pública; el informe agregado conserva procedencia privada y debe revalidarse legalmente antes de publicar datos originales.
