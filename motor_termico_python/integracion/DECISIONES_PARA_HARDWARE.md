# Traspaso a desarrollo de hardware / firmware

**Trabajo del responsable de hardware:** conservar y probar el sistema físico existente. No se espera que implemente los modelos Python dentro del ESP32.

## Contrato y sensado

- Confirmar versión `v=2` y secuencia de 20 bytes en el firmware actual. Un cambio de longitud, escala, UUID o orden de bytes exige actualizar `src/lib/telemetry.js` y `android/.../Telemetry.java`.
- Confirmar si está instalado **HTU21D o AHTx**; el código actual contempla búsqueda de ambos. Registro de modelo real, número de serie, montaje y offset conocido.
- Probar MPU6050, error del índice de movimiento y sensibilidad al movimiento sin desplazamiento; no afirmar que mide gasto metabólico.
- Probar LED RGB, motor, botón largo (actualmente pausa), batería y autonomía real. No confundir pausa con hidratación declarada.
- D4/SDA y D8/SCL según unidad documentada; D5 tiene daño reportado. Revisar cableado real antes de escalar.

## Qué entregarle al encargado de software

- `firmware_version`, `GATT_contract_version`, UUID de servicio/notify/write, ejemplo de bytes crudos y JSON normalizado.
- Frecuencia de muestra, latencia y pérdida de paquetes.
- Comportamiento offline y vigencia de estados LED cuando se pierde el enlace.
- Estados observados del botón, vibración y pauseRequest.
- Calibración preliminar T/RH al sol/sombra, tiempo de respuesta y autorcalentamiento.
- Consumo por modo (espera, BLE, medición, vibración), batería y autonomía medida.

## Posible extensión radiativa compacta

**Solo diseño experimental:** dos superficies térmicas diferenciales con absorptividad contrastante; registrar Tnegra/Tclara, orientación, viento, montaje y hora. La diferencia térmica NO puede convertirse a W/m² sin calibración. Alternativas de bajo costo: luxómetro como indicador de sombra (no radiación total), meteorología externa por zona, datos del supervisor. Si no hay instrumentación calibrada, mantener `radiation=unknown`.

## Riesgo de alertas simultáneas

El firmware v2 ya decide pausas por Heat Index y movimiento. El backend Python aún no tiene autoridad sobre actuadores de ese contrato. Antes del piloto, el equipo debe **definir quién manda alertas y qué prioridad tienen**, para no generar mensajes contradictorios. Validar con prevención las reglas y la respuesta que debe adoptar el trabajador.
