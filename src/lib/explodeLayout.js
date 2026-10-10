// Despiece de los componentes internos. Cada pieza se separa de las demás en z (capas entre la tapa
// y la batería) y un poco en el plano xy, para que ninguna tape a otra al explosionar.
// Los valores son desplazamientos (mm) respecto de su posición ensamblada, a explosión = 1.
import * as THREE from 'three';

const LAYOUT = {
  ant: [-2, 8, -6],      // antena FPC pegada a la tapa: apenas se despega, sube hacia +y
  led1: [-3, -6, -9],    // LED de estado
  led2: [5, -7, -9],     // LED de batería
  sw: [9, 8, -4],        // interruptor, hacia la pared lateral que lo aloja
  motor: [0, 6, -14],
  mpu: [-8, -6, -18],    // acelerómetro
  htu: [-12, 0, -22],    // sensor T/HR: sale hacia la rejilla (−x)
  btn: [14, 8, -10],     // pulsador de hidratación: se separa de la pared superior
  xiao: [10, -8, -26],   // placa principal: la capa más profunda antes de la batería
};

export const PART_KEYS = Object.keys(LAYOUT);

export function partOffset(key, e, out = new THREE.Vector3()) {
  const l = LAYOUT[key];
  if (!l) return out.set(0, 0, 0);
  return out.set(l[0] * e, l[1] * e, l[2] * e);
}

// Qué pieza arrastra a cada punto de interés
export const HOTSPOT_PART = {
  sensor: 'htu', 'led-estado': 'led1', 'led-bateria': 'led2', usb: 'xiao', switch: 'sw',
  antena: 'ant', acel: 'mpu', xiao: 'xiao', motor: 'motor', boton: 'btn',
};
