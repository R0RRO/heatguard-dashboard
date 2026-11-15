// Datos del producto HeatGuard Clip v2 (fuente: documento técnico del proyecto).
// Coordenadas de los puntos de interés en mm, ya en el espacio del visor 3D:
// x = largo, y = alto, z = hacia el frente (cara con sensor y LED).

export const HOTSPOTS = [
  { id: 'sensor', n: 1, group: 'front', pos: [-30, 0, 8.8], normal: [0, 0, 1],
    title: 'Sensor de temperatura y humedad',
    desc: 'HTU21D (±0,3 °C) detrás de una rejilla hexagonal. Va en una cámara aislada de la electrónica, con ventilación arriba, abajo y al costado, para medir el aire y no el calor del propio clip.' },
  { id: 'led-estado', n: 2, group: 'front', pos: [5, -9, 11.4], normal: [0, 0, 1],
    title: 'LED de estado',
    desc: 'Verde parpadeante = condición óptima · amarillo = cansancio · rojo + vibración = toca descanso · azul fijo = en pausa · azul parpadeante + vibración = pausa cumplida. El clip calcula la exposición acumulada (calor + movimiento) y decide solo, con o sin el panel.' },
  { id: 'led-bateria', n: 3, group: 'front', pos: [12.5, -9, 11.4], normal: [0, 0, 1],
    title: 'LED de batería',
    desc: 'LED bicolor: al encender muestra 3 s el nivel de batería (rojo parpadeante bajo 20 %, rojo hasta 50 %, azul parpadeante hasta 80 %, azul sobre 80 %).' },
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
    desc: 'GY-521 (MPU6050). Entrega un índice de movimiento que se suma, junto con el calor, a la exposición acumulada. Describe cuánto se mueve el clip; no mide la tasa metabólica.' },
  { id: 'xiao', n: 8, group: 'front', pos: [26.5, -7.9, 1], normal: null, interior: true,
    title: 'Microcontrolador',
    desc: 'Seeed XIAO ESP32-C3: Bluetooth 5, cargador LiPo integrado y antena externa.' },
  { id: 'motor', n: 9, group: 'front', pos: [26, 6.5, 5], normal: null, interior: true,
    title: 'Motor de vibración',
    desc: 'Motor de 3 V (con transistor 2N2222). Cuando toca descanso vibra 5 veces cada 40 s; al cumplirse la pausa vuelve a vibrar hasta que el trabajador la cierre.' },
  { id: 'boton', n: 11, group: 'front', pos: [9, 21.6, 2.5], normal: [0, 1, 0],
    title: 'Botón de pausa',
    desc: 'Pulsador en la pared superior. Hay que mantenerlo presionado 2 s, para que no se active por accidente: la primera vez comienza la pausa de hidratación y descanso (LED azul fijo) y la segunda la termina. Nadie entra ni sale de una pausa en el panel sin presionarlo.' },
  { id: 'bateria', n: 10, group: 'battery', pos: [5, 0, -3.6], normal: null, interior: true,
    title: 'Batería',
    desc: 'LiPo 523450, 3,7 V y 1000 mAh, con circuito de protección (PCM) y conector PH2.0.' },
];

export const LED_STATES = {
  normal:    { label: 'Óptimo',         color: '#22c55e', blink: 'slow', vibrate: false, text: 'Verde parpadeante: condición óptima. El clip solo acumula la exposición.' },
  cansancio: { label: 'Cansancio',      color: '#eab308', blink: null, vibrate: false, text: 'Amarillo: la exposición acumulada pasó el umbral de cansancio. Se acerca la pausa.' },
  descanso:  { label: 'Toca descanso',  color: '#ef4444', blink: null, vibrate: true, text: 'Rojo y 5 vibraciones cada 40 s: toca la pausa de hidratación y descanso. Mantener el botón 2 s para comenzarla.' },
  pausa:     { label: 'En pausa',       color: '#3b82f6', blink: null, vibrate: false, text: 'Azul fijo: en pausa. La exposición acumulada baja mientras dura.' },
  finPausa:  { label: 'Pausa cumplida', color: '#3b82f6', blink: 'fast', vibrate: true, text: 'Azul parpadeante y vibración: se cumplió el tiempo de pausa. Mantener el botón 2 s para volver al trabajo.' },
};

export const SPECS = [
  { title: 'Medidas', rows: [['Carcasa', '80 × 40 × 17 mm'], ['Con clip de chaleco', '≈ 28 mm de espesor'], ['Material', 'ASA o PETG, color claro']] },
  { title: 'Sensado', rows: [['Temperatura y humedad', 'HTU21D · ±0,3 °C'], ['Movimiento', 'MPU6050 (acelerómetro)'], ['Indicador térmico', 'Sensación térmica: Heat Index del NWS (auxiliar, no WBGT)'], ['Exposición acumulada', 'Calor × movimiento (regla sin validar)']] },
  { title: 'Alertas y entradas', rows: [['Estado', 'LED RGB: verde / amarillo / rojo / azul'], ['Batería', 'LED bicolor rojo / azul'], ['Aviso físico', 'Vibración'], ['Botón', 'Pausa · mantener 2 s']] },
  { title: 'Conectividad y energía', rows: [['Radio', 'Bluetooth LE 5'], ['Batería', 'LiPo 3,7 V · 1000 mAh'], ['Carga', 'USB-C (~100 mA)']] },
];

export const COMPONENTS = [
  ['Seeed XIAO ESP32-C3', 'Microcontrolador, Bluetooth y carga LiPo', '—'],
  ['HTU21D (GY-21)', 'Temperatura y humedad ambiente', 'I2C 0x40'],
  ['MPU6050 (GY-521)', 'Índice de movimiento (exposición acumulada)', 'I2C 0x68'],
  ['Motor plano 3 V + 2N2222', 'Alerta por vibración', 'D7'],
  ['LED RGB de estado', 'Verde / amarillo / rojo / azul', 'D2, D3, D6'],
  ['LED bicolor de batería', 'Nivel al encender', 'D9, D10'],
  ['Pulsador táctil 6×6 + tapa', 'Comenzar y terminar la pausa', 'D0 → GND (pull-up interno)'],
  ['LiPo 523450 con PCM', 'Energía, con interruptor', 'D1 (divisor)'],
];

// Señales del clip hacia el trabajador (simulación en la vista Producto)
export const SIGNALS = {
  registro: { label: 'Botón mantenido', color: '#22c55e', text: 'El clip confirma con una vibración.' },
  recordatorio: { label: '—', color: '#22d3ee', text: '' },
};

export const MOUNTS = {
  none: { label: 'Sin accesorio', text: 'Solo la carcasa de dos piezas (tapa frontal y base trasera).' },
  clip: { label: 'Clip de chaleco', text: 'Lengüeta elástica de PETG para enganchar en el chaleco o la ropa de alta visibilidad.' },
  casco: { label: 'Placa de casco', text: 'Placa cóncava (radio 110 mm) que se pega al costado del casco con cinta VHB, sin perforarlo.' },
};
