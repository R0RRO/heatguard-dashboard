# Módulo radiativo diferencial futuro

## Propuesta concreta

Añadir a la cara exterior del clip dos islas térmicas simétricas de aproximadamente 8–10 mm, una negra de alta absortividad y otra blanca reflectante. Cada isla se mide con un sensor digital TMP117 montado en la misma geometría y con mínima conducción hacia la placa. La diferencia `T_negra − T_blanca` se transmite como señal radiativa cruda.

Esta geometría aprovecha el principio negro/blanco de los piranómetros de termopila: la respuesta nace de una diferencia térmica inducida por radiación. Ese principio está documentado en diseños de piranómetros ([artículo AMS](https://journals.ametsoc.org/view/journals/atot/15/3/1520-0426_1998_015_0677_iipd_2_0_co_2.xml)) y en el [Best Practices Handbook for Radiometers de NREL](https://docs.nrel.gov/docs/fy24osti/88300.pdf). Un par económico en una carcasa wearable no hereda, por semejanza, la calibración ni la trazabilidad de esos instrumentos.

## Componentes y conexión

| Elemento | Propuesta | Motivo |
|---|---|---|
| Sensores | 2 × TMP117, direcciones 0x48 y 0x49 | Resolución 0,0078 °C, hasta ±0,1 °C entre −20 y 50 °C y consumo típico de pocos µA a baja tasa, según [datasheet TI](https://www.ti.com/lit/ds/symlink/tmp117.pdf) |
| Superficie negra | Cobre fino o foil con recubrimiento negro mate estable | Maximizar absorción relativa |
| Superficie blanca | Geometría idéntica, recubrimiento blanco reflectante estable | Referencia radiativa/conductiva |
| Aislamiento | Ranuras, cuello flex o sustrato de baja conductividad | Reducir conducción común hacia PCB/carcasa |
| Bus | I²C existente: D4/SDA y D8/SCL | Coincide con `Wire.begin(D4, D8)` del firmware real revisado |
| Muestreo inicial | 1 Hz y filtrado temporal trazable | Adecuado para caracterizar respuesta; optimizable después de medir consumo |

Los 8–10 mm son una **hipótesis mecánica inicial**, no una dimensión validada. Debe comprobarse área efectiva, separación, masa térmica, comodidad y resistencia del recubrimiento antes de congelar la carcasa.

## Integración mínima

1. Colocar las dos islas en la cara expuesta, lejos del cuerpo, batería, regulador y ESP32.
2. Mantener misma área, espesor, adhesivo, sensor, pistas y orientación; cambiar solo acabado óptico.
3. Añadir ranuras o un flex corto para disminuir conducción, sin debilitar el clip.
4. Leer ambos TMP117 en el bus I²C existente y transmitir temperaturas y diferencial.
5. Registrar temperatura interna/ambiente, orientación y viento si están disponibles.
6. No convertir el diferencial a W/m² hasta obtener un modelo calibrado y validado fuera de muestra.

En la placa física actual **D5 no debe utilizarse**: el firmware documenta que quedó en corto con GND y trasladó SCL a D8. La ampliación debe compartir D4/D8 o incorporar un multiplexor compatible si las direcciones I²C efectivas entran en conflicto. Esta corrección prevalece sobre la propuesta v0.30 basada en el pinout genérico de la placa.

La interfaz de software v0.30 ya admite temperaturas de superficie y diferencial con procedencia manual o simulada. La futura característica BLE deberá versionarse; no debe reutilizar un paquete existente sin un campo de versión y longitud.

## Alternativa de iluminancia

Un VEML7700 puede ayudar a clasificar luz visible, sol/sombra o detectar cambios. Es un sensor de luz ambiental visible de 16 bits e I²C ([datasheet Vishay](https://www.vishay.com/docs/84286/veml7700.pdf)); no mide por sí solo irradiancia térmicamente relevante, radiación infrarroja total ni WBGT. Se propone solo como clasificador auxiliar y no como conversión universal de lux a W/m².

## Modelo físico que deberá calibrarse

De forma conceptual:

```text
ΔT = f(irradiancia, absortividades, convección, orientación,
       geometría, temperatura ambiente, conducción y tiempo)
```

La convección cambia con viento y movimiento; la orientación cambia la radiación incidente; la carcasa introduce conducción y sombra; las superficies envejecen. Por eso una curva de `ΔT → W/m²` obtenida en aire quieto no es válida automáticamente en terreno.

## Ensayo de calibración

Registrar simultáneamente:

- `T_negra`, `T_blanca`, `ΔT`, temperatura/humedad del clip y temperatura interna;
- irradiancia de un piranómetro/radiómetro de referencia;
- WBGT/TGBH de instrumento profesional separado;
- viento a 0, 1, 2 y 4 m/s o los puntos alcanzables y medidos;
- orientación frontal, ±45°, lateral y sombra parcial;
- ciclos de subida/bajada de radiación, al menos tres niveles y repeticiones;
- estado de batería, potencia de radio y temperatura del cuerpo simulado.

Separar calibración y evaluación por días o montajes. Reportar MAE, sesgo, histéresis, constante de tiempo, repetibilidad, deriva, sensibilidad al viento y error por orientación. NREL señala que radiometros térmicos pueden tener respuestas del orden de segundos a decenas de segundos; la respuesta real de este módulo debe medirse, no suponerse.

## Criterios de avance de etapa

| Etapa | Criterio |
|---|---|
| Banco | Dos canales estables, sin saturación, direcciones únicas y ruido documentado |
| Cámara | Modelo calibrado con error, intervalo y dominio de viento/orientación declarados |
| Carcasa | Sesgo por electrónica/cuerpo cuantificado y aceptable para el objetivo aprobado |
| Campo | Evaluación independiente con condiciones no usadas en calibración |
| Producto | Repetibilidad entre unidades, envejecimiento, consumo, EMC y seguridad comprobados |

Hasta superar estas etapas, el diferencial se mostrará como **señal experimental**, no irradiancia certificada ni WBGT.
