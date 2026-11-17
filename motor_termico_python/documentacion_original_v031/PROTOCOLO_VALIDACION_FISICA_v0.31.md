# Protocolo de validación física v0.31

Este documento define la siguiente etapa; no contiene resultados físicos. Debe ejecutarse con personal competente, instrumentos trazables y una matriz de riesgos aprobada. No probar sobre trabajadores hasta cerrar las fases de banco.

## 1. Registro previo

Documentar por unidad: número de activo, MAC/identidad BLE, revisión de PCB, firmware/commit, sensores instalados, batería, fecha, operador y fotografías. Verificar visualmente SDA D4, SCL D8 y que D5 no esté conectado.

Criterio de entrada: ninguna conexión improvisada, daño, conductor expuesto o discrepancia con el plano aprobado.

## 2. Banco eléctrico

Medir tensión, corriente en reposo/publicidad/conexión/notificación, temperatura de componentes y consumo de LED/motor. Probar fuente limitada en corriente, protección del motor y apagado por duración.

Criterio de aceptación: límites definidos por ingeniería antes del ensayo; ausencia de calentamiento, reinicio, batería fuera de rango o actuador atascado. Registrar valores, no usar “funciona” como medida.

## 3. Auditoría GATT real

Para cada característica confirmar UUID, propiedades, longitud, endianess, tasa y valores límite. Repetir en Windows y en el gateway Linux objetivo si aplica. Capturar tráfico y hora del gateway.

Criterio: cero discrepancias sin resolver frente a `BLE_V031.md`; cualquier cambio obliga a versionar protocolo y actualizar pruebas.

## 4. Botón

Ejecutar al menos 30 pulsaciones cortas, 30 largas alrededor de 1 s y series con rebote/rapidez. Repetir tras desconexión, reinicio de clip, reinicio de gateway, wrap inducido y dos clips simultáneos.

Registrar enviados, recibidos, duplicados, saltos y reinicios. Criterio provisional de ingeniería: 100 % de eventos deliberados presentes una vez en DB; cualquier pérdida se investiga. La pulsación larga debe mostrarse siempre como autodeclarada/no fisiológica.

## 5. Radio y recuperación

Ensayar distancias y orientaciones representativas, cuerpo/ropa como obstáculo, coexistencia y seis clips. Cortar Bluetooth, red, API y energía del gateway por separado. Confirmar que la outbox crece, el error es visible y la entrega posterior no duplica.

Criterio: recuperación documentada sin pérdida silenciosa; tiempos y tasas se informan con intervalos, no con una única observación.

## 6. Temperatura y humedad

Comparar cada clip con referencias calibradas en varios puntos estables y transiciones: al menos ambiente templado, cálido, húmedo y seco dentro del rango esperado. Controlar tiempo de estabilización, posición, radiación y autocalentamiento.

Antes de ejecutar, fijar junto al metrólogo MAE, sesgo, repetibilidad, histéresis y error máximo permitidos para el uso previsto. No elegir límites después de ver los resultados.

## 7. Movimiento, pasos y batería

Comparar pasos con conteo independiente en reposo, marcha y trabajo manual; evaluar falsos pasos. Medir deriva de orientación, saturación y reinicio del contador. Para batería, descargar varias unidades bajo perfiles reales y relacionar voltaje/porcentaje/tiempo.

Criterio: reportar curvas y dispersión. No presentar el porcentaje firmware como estado de carga preciso sin calibración.

## 8. Radiación diferencial futura

Montar superficies negra/blanca con geometría reproducible. Comparar delta térmica contra piranómetro o referencia radiativa trazable bajo sol, sombra, nubosidad, viento, orientaciones y transitorios. Registrar D4/D8, nunca D5.

Criterio: modelo calibrado con incertidumbre, dominio de validez, tiempo de respuesta y detección de fuera de dominio. Hasta entonces la señal es experimental y no W/m² medido.

## 9. Comparación térmica de sistema

Usar instrumento y procedimiento apropiados al objetivo, registrar simultáneamente microclima, posición, ropa, actividad y fuentes. Separar interior/exterior y no sustituir un valor regional por el puesto.

Analizar sesgo, MAE/RMSE, errores cerca de cortes, falsos bajos, variación por clip/sitio y cobertura de intervalos. La aprobación ocupacional requiere revisión profesional y normativa aplicable; el software no la otorga.

## 10. Ensayo de panel y operación

Con supervisores de prueba, verificar asociación correcta, múltiples clips, desconexión visible, edad de datos, trabajo/descanso, hidratación, procedencia, exportación y recuperación. Simular clave inválida, evento tardío, datos contradictorios y sensor ausente.

Criterio: el usuario distingue dato medido, estimado, supuesto y simulado; no interpreta hidratación como fisiología ni ausencia de alerta como seguridad.

## Registro mínimo por caso

`case_id`, fecha UTC/local, unidad, firmware, instrumentos/calibración, configuración, condiciones, acción, dato bruto, dato backend, resultado esperado, resultado observado, desviación, evidencia y firma del responsable.

## Puertas de liberación

1. Banco eléctrico aprobado.
2. Contrato GATT y recuperación aprobados.
3. Sensores y batería caracterizados.
4. Radiación caracterizada o deshabilitada con límite visible.
5. Comparación térmica y riesgos revisados por profesional competente.
6. Ciberseguridad, privacidad, capacitación y respuesta operativa aprobadas.

Un fallo en una puerta bloquea la siguiente. Las simulaciones de v0.31 no pueden usarse como sustituto de evidencia física.
