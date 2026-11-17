# Avisos de software y datos de terceros

Este archivo es un inventario técnico, no asesoría legal. Antes de distribuir comercialmente una imagen con dependencias instaladas, genere y revise un SBOM y conserve las licencias completas incluidas por cada paquete.

## Código HeatGuard

El material entregado por el usuario y sus modificaciones no incluían una licencia raíz explícita. Esta entrega **no inventa ni concede una licencia** sobre HeatGuard. El titular debe definir autoría y licencia antes de publicar o comercializar el código.

## Dependencias directas

| Componente | Uso | Licencia indicada por el paquete instalado durante la verificación |
|---|---|---|
| FastAPI | API | MIT |
| Uvicorn | Servidor ASGI | BSD-3-Clause |
| Bleak | BLE | MIT |
| scikit-learn | ML exploratorio | BSD-3-Clause |
| NumPy | Cálculo | BSD-3-Clause y licencias de componentes incluidas |
| pandas | Datos | BSD-3-Clause |
| joblib | Artefactos ML | BSD-3-Clause |
| Matplotlib | Gráficos de investigación | Licencia Matplotlib y licencias de componentes/fuentes |
| lwbgt 1.2.1 | Implementación Liljegren | `Apache-2.0 AND LicenseRef-UChicago-Argonne-WBGT-1.1` |

La licencia compuesta de `lwbgt` merece revisión antes de una distribución comercial. El paquete declara Apache-2.0 para parte del trabajo y términos/NOTICE asociados a la implementación modificada de Argonne. Consulte los archivos `LICENSE*` y `NOTICE*` de la versión instalada; no copie un binario o código de esa dependencia sin conservar las condiciones aplicables.

Las dependencias transitivas poseen sus propias licencias. La fuente definitiva es la distribución instalada, no esta tabla abreviada.

## Datos y servicios

Los resultados históricos incorporan datos o respuestas atribuibles a Open-Meteo, Japan Meteorological Agency y Japan Ministry of the Environment según los manifiestos en `research_data/` y los informes de resultados. Los archivos `FUENTE_LOCAL_SHA256.json` y `ORIGEN_Y_SHA256.json` preservan origen y huellas. Revise condiciones de reutilización de cada proveedor antes de redistribuir los datos fuera del propósito de investigación.

## Artículos y normas

Las referencias científicas enlazadas se citan, no se redistribuyen. ISO 7243 y otras normas completas pueden estar sujetas a derechos de autor; el repositorio solo enlaza sus fichas oficiales y no incorpora el texto normativo.

## Modelos serializados

Los archivos `.joblib` incluidos son resultados de investigación `NO_DESPLEGAR`. Además de su licencia, `joblib` usa serialización compatible con pickle: cargar un artefacto no confiable puede ejecutar código. HeatGuard exige una huella SHA-256 configurada, pero una huella solo verifica identidad; no convierte un archivo de origen desconocido en seguro.

