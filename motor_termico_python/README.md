# HeatGuard · Motor de análisis térmico en Python

**Subproyecto para integración — basado en HeatGuard Backend v0.31 STABLE.** Fecha de preparación: 17 de noviembre de 2026. Esta carpeta está diseñada para incorporarse sin interferir con el frontend React, `server/` Node, app Android o firmware del repositorio principal.

> **Importante:** este módulo NO es el firmware que hoy controla la vibración y las pausas, NO está integrado automáticamente al servidor Node existente, NO mide WBGT mediante el clip actual y NO representa un instrumento ISO 7243 certificado. No usar los algoritmos experimentales como única protección ocupacional.

## Qué aporta

- Motor Python con validación y procedencia de datos de temperatura, humedad, radiación, viento, movimiento y batería.
- Estimación WBGT exterior condicionada a datos suficientes mediante Ono; análisis alternativo Liljegren cuando corresponde.
- Cálculo auxiliar de Heat Index y aproximaciones experimentales identificadas.
- Registro de exposición temporal, pausas y calidad de datos, base SQLite y API de laboratorio FastAPI.
- Experimentación con ML y evaluación de incertidumbre; **no hay garantía de generalización a obras reales**.
- API/panel de laboratorio independiente de la aplicación React.
- Adaptador **lógico** probado para recibir el contrato de telemetría `v=2` del repositorio actual y convertirlo en observaciones del motor; no decodifica radio GATT ni altera el firmware.

## Arquitectura del equipo (sin romper el proyecto existente)

```text
ESP32-C3 ── BLE v2 ──> App Android / navegador ──> Node server/index.js ──> Dashboard React
       (firmware actual, Heat Index y pausas locales)
                              |
                              | [FUTURA integración backend-backend]
                              v
                integracion/telemetry_v2_adapter.py
                              |
                              v
                    heatguard/ + FastAPI
             WBGT estimado cuando haya entradas suficientes
               y métricas experimentales de incertidumbre
```

El servidor Node debe seguir siendo fuente principal de identidad, autenticación, pausa y mando remoto. No hay que enviar comandos desde **dos motores de alertas** al mismo LED/motor sin decidir antes la autoridad y los modos piloto.

## Dónde colocar la carpeta en GitHub

`R0RRO/heatguard-dashboard/motor_termico_python/`

No reemplazar `src/`, `server/`, `android/`, `firmware/`, `panel_pruebas/` ni el contrato existente en `docs/contrato-datos.md`.

## Instalación local (Python 3.10+, Windows)

Desde `motor_termico_python/`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[api,test,ml]"
.\.venv\Scripts\python.exe -m pytest -q
$env:HG_ENABLE_DEMO="1"
$env:HG_DB_PATH="data/heatguard_laboratorio.sqlite"
$env:HG_ADMIN_API_KEY="CLAVE_LARGA_PARA_LABORATORIO"
$env:HG_VIEWER_API_KEY="OTRA_CLAVE_LARGA"
.\.venv\Scripts\python.exe -m uvicorn heatguard.api:app --host 127.0.0.1 --port 8000
```

Abrir http://127.0.0.1:8000/mvp. Esta es la UI **del laboratorio Python**, no el dashboard React del equipo. No publicar directamente la API en internet.

### Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[api,test,ml]'
.venv/bin/python -m pytest -q
```

## Reproducción comprobada

- ZIP completo de origen `HeatGuard_Clip_v0.31_STABLE.zip`: **212 pruebas** aprobadas en entorno local con fuentes históricas presentes.
- Carpeta pública depurada: **181 pruebas** aprobadas, incluidas cinco del adaptador v2. Se excluyeron siete archivos de test dependientes de datasets externos que no se redistribuyen aquí. No se ha verificado hardware.
- Probar el adaptador: `python -m pytest -q tests/test_contract_v2_adapter.py`.

## Orden de lectura recomendado

1. [`integracion/CONTRATO_Y_PENDIENTES.md`](integracion/CONTRATO_Y_PENDIENTES.md): incompatibilidades BLE y plan seguro de conexión con Node.
2. [`investigacion/RESULTADOS_Y_LIMITACIONES.md`](investigacion/RESULTADOS_Y_LIMITACIONES.md): evidencia de errores y rangos (no validación del clip).
3. [`presentacion/PLAN_FINAL_EQUIPO.md`](presentacion/PLAN_FINAL_EQUIPO.md): qué tiene que terminar cada área antes de pitch/video.
4. [`presentacion/GUIA_PITCH_INVERSORES.md`](presentacion/GUIA_PITCH_INVERSORES.md): discurso, demo, afirmaciones permitidas y riesgos.

## Archivos excluidos deliberadamente

No se añadieron archivos privados, entrevistas, credenciales, bases de datos de usuarios, modelos serializados `.joblib`, datasets históricos en bruto, copias del firmware del compañero ni capturas con información de usuarios. La evidencia estadística se documenta en forma agregada, con fuentes y huellas de los archivos originales conservados de forma privada. Antes de publicar cualquier código/dependencia en un proyecto comercial, revisar autoría, permisos y licencias (ver `THIRD_PARTY_NOTICES.md`).

### Estado de las versiones

- **Código realmente incluido:** v0.31 STABLE, verificado desde ZIP original.
- **Investigación de rangos:** informe retrospectivo agregado, verificable con archivos de investigación privados.
- **v0.32 descrita en conversaciones anteriores:** NO se incorpora porque el artefacto fuente no estaba disponible en esta sesión. No se afirma que su mecanismo de aprendizaje/alertas haya sido desplegado en este repositorio.

## Aviso técnico

No confundir Heat Index (actualmente presente en firmware/React y útil como indicador auxiliar en ciertas condiciones) con **WBGT/TGBH normativo**. ISO 7243 y DS 594 dependen de factores como carga metabólica, vestimenta, aclimatación y tiempos; los colores serían una codificación de HeatGuard, no colores prescritos por ISO.
