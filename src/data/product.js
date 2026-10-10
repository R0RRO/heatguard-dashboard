// Datos del producto HeatGuard Clip v2 (fuente: documento técnico del proyecto).
// Coordenadas de los puntos de interés en mm, ya en el espacio del visor 3D:
// x = largo, y = alto, z = hacia el frente (cara con sensor y LED).

export const HOTSPOTS = [
  { id: 'sensor', n: 1, group: 'front', pos: [-30, 0, 8.8], normal: [0, 0, 1],
    title: 'Sensor de temperatura y humedad',
    desc: 'HTU21D (±0,3 °C) detrás de una rejilla hexagonal. Va en una cámara aislada de la electrónica, con ventilación arriba, abajo y al costado, para medir el aire y no el calor del propio clip.' },
  { id: 'led-estado', n: 2, group: 'front', pos: [5, -9, 11.4], normal: [0, 0, 1],
    title: 'LED de estado',
    desc: 'Semáforo del trabajador: verde = condiciones normales, azul = atención, rojo = riesgo alto (acompañado de vibración).' },
  { id: 'led-bateria', n: 3, group: 'front', pos: [12.5, -9, 11.4], normal: [0, 0, 1],
    title: 'LED de batería',
    desc: 'Se enciende en rojo cuando la carga de la batería está baja.' },
  { id: 'usb', n: 4, group: 'front', pos: [40.3, -7.9, 3.1], normal: [1, 0, 0],
    title: 'Puerto USB-C',
    desc: 'Carga la batería y sirve para programar el firmware sin abrir la carcasa. La XIAO carga a ~100 mA.' },
  { id: 'switch', n: 5, group: 'front', pos: [25.3, 20.3, 2], normal: [0, 1, 0],
    title: 'Interruptor',
    desc: 'Interruptor deslizante que corta la batería. Con el clip apagado no carga.' },
  { id: 'antena', n: 6, group: 'front', pos: [0, 8, 6.5], normal: null, interior: true,
    title: 'Antena Bluetooth',
    desc: 'Antena FPC de 40 × 20 mm pegada a la cara interior frontal, detrás del logo y sin metal encima.' },
  { id: 'acel', n: 7, group: 'front', pos: [-9.7, -9.5, 5.8], normal: null, interior: true,
    title: 'Acelerómetro',
    desc: 'GY-521 (MPU6050). Mide actividad, pasos, inmovilidad prolongada y posibles caídas.' },
  { id: 'xiao', n: 8, group: 'front', pos: [26.5, -7.9, 1], normal: null, interior: true,
    title: 'Microcontrolador',
    desc: 'Seeed XIAO ESP32-C3: Bluetooth 5, cargador LiPo integrado y antena externa.' },
  { id: 'motor', n: 9, group: 'front', pos: [26, 6.5, 5], normal: null, interior: true,
    title: 'Motor de vibración',
    desc: 'Motor plano de 3 V (con transistor 2N2222). Avisa al trabajador cuando pasa a riesgo alto.' },
  { id: 'boton', n: 11, group: 'front', pos: [9, 21.6, 2.5], normal: [0, 1, 0],
    title: 'Botón de hidratación',
    desc: 'Pulsador en la pared superior con tapa de goma azul. Cuando el clip recuerda beber agua (vibración corta y LED celeste), el trabajador lo mantiene presionado ~1 s para registrar que tomó agua: el LED parpadea en verde dos veces y el panel guarda la hora. Es un registro autodeclarado; no reinicia el riesgo térmico ni las alertas.' },
  { id: 'bateria', n: 10, group: 'battery', pos: [5, 0, -3.6], normal: null, interior: true,
    title: 'Batería',
    desc: 'LiPo 523450, 3,7 V y 1000 mAh, con circuito de protección (PCM) y conector PH2.0.' },
];

export const LED_STATES = {
  normal:   { label: 'Normal',      color: '#22c55e', text: 'Condiciones normales. El clip solo monitorea.' },
  atencion: { label: 'Atención',    color: '#3b82f6', text: 'El riesgo aumenta: conviene pausar, hidratarse y buscar sombra.' },
  alerta:   { label: 'Riesgo alto', color: '#ef4444', text: 'LED rojo y vibración: detenerse y recuperarse.' },
};

export const SPECS = [
  { title: 'Medidas', rows: [['Carcasa', '80 × 40 × 17 mm'], ['Con clip de chaleco', '≈ 28 mm de espesor'], ['Material', 'ASA o PETG, color claro']] },
  { title: 'Sensado', rows: [['Temperatura y humedad', 'HTU21D · ±0,3 °C'], ['Movimiento', 'MPU6050 (acelerómetro)'], ['Exposición', 'Tiempo acumulado sobre umbral']] },
  { title: 'Alertas y entradas', rows: [['Estado', 'LED RGB: verde / azul / rojo'], ['Batería', 'LED rojo'], ['Aviso físico', 'Vibración'], ['Botón', 'Hidratación · pulsación larga ~1 s']] },
  { title: 'Conectividad y energía', rows: [['Radio', 'Bluetooth LE 5'], ['Batería', 'LiPo 3,7 V · 1000 mAh'], ['Carga', 'USB-C (~100 mA)']] },
];

export const COMPONENTS = [
  ['Seeed XIAO ESP32-C3', 'Microcontrolador, Bluetooth y carga LiPo', '—'],
  ['HTU21D (GY-21)', 'Temperatura y humedad ambiente', 'I2C 0x40'],
  ['MPU6050 (GY-521)', 'Movimiento e inmovilidad', 'I2C 0x68'],
  ['Motor plano 3 V + 2N2222', 'Alerta por vibración', 'D7'],
  ['LED RGB de estado', 'Verde / azul / rojo', 'D2, D3, D6'],
  ['LED RGB de batería', 'Batería baja (canal rojo)', 'D10'],
  ['Pulsador táctil 6×6 + tapa', 'Registrar hidratación (autodeclarado)', 'D0 → GND (pull-up interno)'],
  ['LiPo 523450 con PCM', 'Energía, con interruptor', 'D1 (divisor)'],
];

// Señales del clip hacia el trabajador (simulación en la vista Producto)
export const SIGNALS = {
  recordatorio: { label: 'Recordatorio de hidratación', color: '#22d3ee', text: 'LED celeste que late despacio y vibración corta: es hora de tomar agua.' },
  registro: { label: 'Hidratación registrada', color: '#22c55e', text: 'Tras la pulsación larga: el LED parpadea dos veces en verde y vibra una vez.' },
};

export const MOUNTS = {
  none: { label: 'Sin accesorio', text: 'Solo la carcasa de dos piezas (tapa frontal y base trasera).' },
  clip: { label: 'Clip de chaleco', text: 'Lengüeta elástica de PETG para enganchar en el chaleco o la ropa de alta visibilidad.' },
  casco: { label: 'Placa de casco', text: 'Placa cóncava (radio 110 mm) que se pega al costado del casco con cinta VHB, sin perforarlo.' },
};
