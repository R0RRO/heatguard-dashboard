# Panel de pruebas del prototipo

Herramientas para probar el hardware del HeatGuard Clip (XIAO ESP32-C3) por USB y Bluetooth,
separadas del dashboard web. Nada de esta carpeta se publica con el sitio.

## Contenido

| Ruta | Qué es |
|---|---|
| `demo_ble/index.html` | Mini app que se conecta al clip por Bluetooth: temperatura, humedad, batería, pasos, distancia, recorrido estimado, orientación y control del LED RGB. Incluye un modo demo con datos simulados. |
| `demo_ble.sh` | Abre la mini app en `http://localhost:8765` (Bluetooth web exige localhost o https). |
| `subir_xiao.sh` | Compila y sube un programa a la XIAO con `arduino-cli` (lo instala si falta) y luego lee el puerto serie. |
| `leer_xiao.sh` | Lee 15 s del puerto serie y lo guarda en `xiao_serial.txt`. |
| `firmware/heatguard_demo` | Firmware de la demo por Bluetooth (el que usa la mini app). |
| `firmware/bateria_test` | Lectura del voltaje de batería (divisor en D1). |
| `firmware/sensor_test` | Prueba del sensor de temperatura y humedad. |
| `firmware/ble_temp` | Temperatura, humedad y movimiento por Bluetooth, para ver con nRF Connect. |
| `firmware/diagnostico_i2c`, `buscar_sensores`, `i2c_manual` | Diagnóstico del bus I2C. |

## Uso

```bash
cd panel_pruebas
./subir_xiao.sh firmware/heatguard_demo   # con la XIAO por USB y el interruptor apagado
./demo_ble.sh                             # abre la app en Chrome, Chromium o Edge
```

Al encender, dejar el clip quieto 2 segundos (calibra el giroscopio).

## Pines en este prototipo

- I2C: SDA en D4 y **SCL en D8** (D5 quedó en corto con GND y no se usa).
- LED de estado RGB, cátodo común: **rojo en D6**, verde en D3, **azul en D2** (cableado al revés del mapa original; corregido en el firmware).
- LED de batería en D10, motor en D7, botón de hidratación en D0, divisor de batería en D1.

## Limitaciones

La distancia es pasos × largo de paso y el recorrido se estima con el giroscopio: es relativo al
punto de inicio, se desvía con el tiempo y no es una posición real (el clip no tiene GPS ni brújula).
El clip mide el ambiente, no la temperatura corporal.
