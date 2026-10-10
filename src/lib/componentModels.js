// Modelos procedurales de los componentes del clip, construidos con las medidas de
// sus hojas de datos / fichas de venta. No son CAD del fabricante: son
// reconstrucciones detalladas (PCB, chips, conectores, cables) para el visor.
//
// Convención local de cada módulo: la placa está en el plano XY con su cara
// de componentes en z = 0 y los componentes crecen hacia +z; x = largo, y = ancho.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0, ...o });
const METAL = (c = '#c9ced6') => std(c, { metalness: 1, roughness: 0.3 });
const BLACK = () => std('#16171a', { roughness: 0.4 });

function rbox(w, h, d, r, material) {
  return new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2 - 0.001, h / 2 - 0.001, d / 2 - 0.001)), material);
}

// Coloca una caja sobre la placa: base en z0, centro (x, y)
function on(group, w, h, d, material, x, y, z0 = 0, r = 0.08) {
  const m = rbox(w, h, d, r, material);
  m.position.set(x, y, z0 + d / 2);
  group.add(m);
  return m;
}

function roundedRectShape(w, h, r) {
  const s = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

function pcb(group, w, h, t, color, r = 0.6) {
  const geo = new THREE.ExtrudeGeometry(roundedRectShape(w, h, r), { depth: t, bevelEnabled: false, curveSegments: 6 });
  const m = new THREE.Mesh(geo, std(color, { roughness: 0.38 }));
  m.position.z = -t; // cara superior en z = 0
  group.add(m);
  return m;
}

// Serigrafía / pads: plano transparente apenas sobre la placa
function silk(group, w, h, draw, px = 80, back = 0) {
  const c = document.createElement('canvas');
  c.width = Math.round(w * px);
  c.height = Math.round(h * px);
  const g = c.getContext('2d');
  g.translate(0, c.height);
  g.scale(px, -px); // coordenadas en mm, y hacia arriba
  draw(g, w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  tex.colorSpace = THREE.SRGBColorSpace;
  const m = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h),
    new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.5, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }),
  );
  if (back) {
    // Cara inferior: el plano mira hacia -z; x local se invierte, así que el texto se lee visto desde atrás
    m.rotation.y = Math.PI;
    m.position.z = -back - 0.012;
  } else {
    m.position.z = 0.012;
  }
  group.add(m);
}

function text(g, str, x, y, size, color = '#ffffff', align = 'center', rot = 0) {
  g.save();
  g.translate(x, y);
  g.scale(1, -1);
  g.rotate(rot);
  g.fillStyle = color;
  g.font = `600 ${size}px "Helvetica Neue", Arial, sans-serif`;
  g.textAlign = align;
  g.textBaseline = 'middle';
  g.fillText(str, 0, 0);
  g.restore();
}

function pad(g, x, y, w, h, color = '#d9a935') {
  g.fillStyle = color;
  g.fillRect(x - w / 2, y - h / 2, w, h);
}

// Pad de estaño (cara trasera) con borde de máscara
function tin(g, x, y, w, h, round = false) {
  g.fillStyle = '#c9ced6';
  if (round) { g.beginPath(); g.arc(x, y, w / 2, 0, Math.PI * 2); g.fill(); } else g.fillRect(x - w / 2, y - h / 2, w, h);
  g.fillStyle = 'rgba(255,255,255,0.45)';
  if (round) { g.beginPath(); g.arc(x - w * 0.12, y + w * 0.12, w * 0.18, 0, Math.PI * 2); g.fill(); } else g.fillRect(x - w / 2 + 0.1, y + h / 2 - 0.22, w - 0.2, 0.12);
}

function hole(g, x, y, ro, ri) {
  g.fillStyle = '#d9a935';
  g.beginPath(); g.arc(x, y, ro, 0, Math.PI * 2); g.fill();
  g.fillStyle = '#0b0b0d';
  g.beginPath(); g.arc(x, y, ri, 0, Math.PI * 2); g.fill();
}

// Resistencias / condensadores SMD
function smd(group, x, y, kind = 'r', rotZ = 0, w = 2.0, h = 1.25) {
  const body = new THREE.Group();
  const d = 0.5;
  on(body, w * 0.62, h, d, kind === 'c' ? std('#a98b5c', { roughness: 0.6 }) : BLACK(), 0, 0, 0, 0.03);
  on(body, w * 0.2, h, d + 0.04, METAL('#cfd3d8'), -w * 0.4, 0, 0, 0.02);
  on(body, w * 0.2, h, d + 0.04, METAL('#cfd3d8'), w * 0.4, 0, 0, 0.02);
  body.position.set(x, y, 0);
  body.rotation.z = rotZ;
  group.add(body);
}

// ─── Seeed Studio XIAO ESP32-C3 (21 × 17,8 mm) ──────────────────────────────
export function buildXiao() {
  const g = new THREE.Group();
  const W = 21, H = 17.8, T = 1.0;
  pcb(g, W, H, T, '#15161a', 0.7);

  silk(g, W, H, (c) => {
    // Pads castellados: 7 por lado largo
    for (let i = 0; i < 7; i++) {
      const x = (i - 3) * 2.54 + 9.4;
      pad(c, x, 0.45, 1.05, 0.9);
      pad(c, x, H - 0.45, 1.05, 0.9);
    }
  });

  // Reverso: pads castellados, pads de batería BAT+ / BAT−, puntos de prueba y serigrafía
  silk(g, W, H, (c) => {
    for (let i = 0; i < 7; i++) {
      const u = W - ((i - 3) * 2.54 + 9.4);
      tin(c, u, 0.45, 1.05, 0.9);
      tin(c, u, H - 0.45, 1.05, 0.9);
    }
    // BAT+ / BAT− (u = 8.5 y 5.5; v = 13.4, ver wiring.js)
    tin(c, 8.5, 13.4, 2.2, 2.2);
    tin(c, 5.5, 13.4, 2.2, 2.2);
    text(c, 'BAT+', 8.5, 15.7, 0.85, '#e8e8ee');
    text(c, 'BAT−', 5.5, 15.7, 0.85, '#e8e8ee');
    // Puntos de prueba
    [[14.8, 4.2], [14.8, 6.4], [16.6, 4.2], [16.6, 6.4], [12.6, 4.2]].forEach(([u, v]) => tin(c, u, v, 0.9, 0.9, true));
    // Serigrafía
    text(c, 'Seeed Studio', 10.5, 10.4, 1.15, '#e8e8ee');
    text(c, 'XIAO ESP32C3', 10.5, 8.6, 1.0, '#e8e8ee');
    text(c, '5V  GND 3V3 D10 D9 D8 D7', 10.5, 2.5, 0.6, '#9aa0aa');
    c.strokeStyle = '#9aa0aa'; c.lineWidth = 0.06; c.strokeRect(1.2, 4.0, 4.4, 3.8);
    text(c, 'ANT', 3.4, 5.9, 0.7, '#9aa0aa');
  }, 80, T);

  // USB-C (extremo +x, ligeramente fuera de la placa)
  const usb = new THREE.Group();
  const usbShell = rbox(7.3, 8.94, 3.2, 0.6, METAL('#d6dae0'));
  usbShell.position.set(0, 0, 1.6);
  usb.add(usbShell);
  const slot = rbox(0.4, 7.7, 2.2, 0.9, std('#050506', { roughness: 0.9 }));
  slot.position.set(3.55, 0, 1.6);
  usb.add(slot);
  const tongue = rbox(0.5, 6.4, 0.6, 0.1, std('#2a2d33'));
  tongue.position.set(3.45, 0, 1.6);
  usb.add(tongue);
  usb.position.set(7.35, 0, 0);
  g.add(usb);

  // Blindaje del ESP32-C3
  const shield = rbox(10.4, 12.2, 1.5, 0.15, METAL('#b9bec6'));
  shield.position.set(-1.8, 0, 0.75);
  g.add(shield);
  for (let i = 0; i < 4; i++) {
    const dimple = new THREE.Mesh(new THREE.CircleGeometry(0.35, 16), std('#8d939c', { metalness: 1, roughness: 0.5 }));
    dimple.position.set(-1.8 + (i % 2 ? 2.4 : -2.4), i < 2 ? 2.4 : -2.4, 1.51);
    g.add(dimple);
  }

  // Conector u.FL de antena
  const ufl = new THREE.Group();
  on(ufl, 2.6, 2.6, 0.8, METAL('#c0c5cc'), 0, 0, 0, 0.1);
  const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.85, 0.85, 0.5, 20), METAL('#e0c36a'));
  ring.rotation.x = Math.PI / 2; ring.position.z = 1.0; ufl.add(ring);
  const core = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.6, 12), std('#111'));
  core.rotation.x = Math.PI / 2; core.position.z = 1.05; ufl.add(core);
  ufl.position.set(-8.8, -2.6, 0);
  g.add(ufl);

  // Botones BOOT / RESET y LEDs de usuario
  on(g, 2.6, 1.9, 1.1, std('#0d0d0f'), 5.2, 6.4, 0, 0.1);
  on(g, 2.6, 1.9, 1.1, std('#0d0d0f'), 5.2, -6.4, 0, 0.1);
  on(g, 1.2, 0.6, 0.4, std('#ff5a36', { emissive: '#ff2200', emissiveIntensity: 0.15 }), -9.4, 5.0, 0, 0.05);
  on(g, 1.2, 0.6, 0.4, std('#ffcc3a'), -9.4, -5.6, 0, 0.05);

  // Pasivos
  [[-8.2, 7.1], [-5.4, 7.1], [-1.6, -7.1], [1.2, 7.1], [-6.8, -7.1], [8.6, -7.1], [8.6, 7.1], [-3.0, 7.1]]
    .forEach(([x, y], i) => smd(g, x, y, i % 3 === 0 ? 'c' : 'r', 0, 1.0, 0.55));
  return g;
}

// ─── GY-521 · MPU-6050 (21 × 16 mm) ─────────────────────────────────────────
export function buildMpu() {
  const g = new THREE.Group();
  const W = 21, H = 16, T = 1.6;
  pcb(g, W, H, T, '#1f3f9c', 0.8);

  silk(g, W, H, (c) => {
    for (let i = 0; i < 8; i++) {
      hole(c, 2.4 + i * 2.54, H - 1.5, 0.75, 0.45);
    }
    const labels = ['VCC', 'GND', 'SCL', 'SDA', 'XDA', 'XCL', 'AD0', 'INT'];
    labels.forEach((l, i) => text(c, l, 2.4 + i * 2.54, H - 3.1, 0.62, '#ffffff'));
    // agujeros de montaje en las dos esquinas del borde opuesto a la cabecera
    hole(c, 1.7, 2.2, 0.95, 0.65);
    hole(c, W - 1.7, 2.2, 0.95, 0.65);
    text(c, 'GY-521', 6.2, 2.6, 1.0, '#ffffff', 'left');
    text(c, 'MPU-6050', 12.6, 7.0, 0.7, '#e8e8ff');
    c.strokeStyle = '#fff'; c.lineWidth = 0.07;
    c.strokeRect(9.4, 5.6, 5.4, 5.4);
  });
  // Reverso: soldaduras de la cabecera, agujeros de montaje y serigrafía
  silk(g, W, H, (c) => {
    for (let i = 0; i < 8; i++) {
      const u = W - (2.4 + i * 2.54);
      tin(c, u, H - 1.5, 1.5, 1.5, true);
      c.fillStyle = '#0b0b0d'; c.beginPath(); c.arc(u, H - 1.5, 0.4, 0, Math.PI * 2); c.fill();
    }
    ['VCC', 'GND', 'SCL', 'SDA', 'XDA', 'XCL', 'AD0', 'INT'].forEach((l, i) => text(c, l, W - (2.4 + i * 2.54), H - 3.0, 0.62, '#ffffff'));
    [[1.7, 2.2], [W - 1.7, 2.2]].forEach(([u, v]) => hole(c, u, v, 0.95, 0.65));
    text(c, 'GY-521', 11, 7.4, 1.5, '#ffffff');
    text(c, 'MPU-6050 · 3-axis accel + gyro', 11, 5.4, 0.62, '#dfe6ff');
    text(c, '3.3 – 5 V · I2C 0x68', 11, 3.9, 0.62, '#dfe6ff');
  }, 80, T);

  const P = new THREE.Group();
  P.position.set(-W / 2, -H / 2, 0);
  g.add(P);
  // MPU-6050 (QFN 4 × 4 × 0,9)
  const chip = on(P, 4, 4, 0.9, BLACK(), 12.1, 8.3, 0, 0.08);
  chip.name = 'mpu';
  const dot = new THREE.Mesh(new THREE.CircleGeometry(0.22, 12), std('#cfcfcf'));
  dot.position.set(10.9, 9.5, 0.91); P.add(dot);

  // Regulador (SOT-223) + pasivos
  on(P, 6.5, 3.5, 1.6, BLACK(), 5.0, 4.4, 0.3, 0.1);
  on(P, 3.0, 1.5, 0.35, METAL('#b9bec6'), 5.0, 6.8, 0.6, 0.05);
  [-1.2, 0, 1.2].forEach((dx) => on(P, 0.5, 1.3, 0.3, METAL('#b9bec6'), 5.0 + dx * 1.0, 2.2, 0.3, 0.03));
  smd(P, 3.0, 8.8, 'c', 0, 1.6, 1.0);
  smd(P, 7.4, 8.8, 'c', 0, 1.6, 1.0);
  smd(P, 16.8, 6.0, 'r', Math.PI / 2, 1.6, 1.0);
  smd(P, 16.8, 9.8, 'r', Math.PI / 2, 1.6, 1.0);
  smd(P, 2.2, 5.0, 'r', Math.PI / 2, 1.6, 1.0);
  on(P, 1.6, 0.8, 0.45, std('#ff3b30', { emissive: '#ff1a00', emissiveIntensity: 0.2 }), 9.2, 2.6, 0, 0.05);
  return g;
}

// ─── GY-21 · HTU21D (13,5 × 10,5 mm) ────────────────────────────────────────
export function buildHtu() {
  const g = new THREE.Group();
  const W = 13.5, H = 10.5, T = 1.0;
  pcb(g, W, H, T, '#2145a8', 0.6);

  silk(g, W, H, (c) => {
    [1.3, 3.84, 6.38, 8.92].forEach((y) => hole(c, 1.2, y, 0.65, 0.4));
    ['VIN', 'GND', 'SCL', 'SDA'].forEach((l, i) => text(c, l, 3.2, 1.3 + i * 2.54, 0.55, '#fff', 'left'));
    text(c, 'GY-21', 9.0, 2.0, 0.8, '#fff');
    text(c, 'HTU21', 9.0, 8.8, 0.7, '#e8e8ff');
  });

  // Reverso: soldaduras de las 4 patas y serigrafía
  silk(g, W, H, (c) => {
    [1.3, 3.84, 6.38, 8.92].forEach((v) => { tin(c, W - 1.2, v, 1.3, 1.3, true); });
    ['VIN', 'GND', 'SCL', 'SDA'].forEach((l, i) => text(c, l, W - 3.2, 1.3 + i * 2.54, 0.55, '#fff', 'right'));
    text(c, 'GY-21', 5.2, 6.4, 1.0, '#ffffff');
    text(c, 'HTU21D · I2C 0x40', 5.2, 4.2, 0.55, '#dfe6ff');
  }, 80, T);

  const P = new THREE.Group();
  P.position.set(-W / 2, -H / 2, 0);
  g.add(P);
  // Sensor HTU21D (DFN 3 × 3 × 0,9) con ventana de medición
  const body = on(P, 3, 3, 0.9, std('#b9bcc2', { metalness: 0.4, roughness: 0.35 }), 8.4, 5.2, 0, 0.1);
  body.name = 'htu';
  const win = new THREE.Mesh(new THREE.CircleGeometry(0.7, 20), std('#e9d38a', { roughness: 0.2 }));
  win.position.set(8.4, 5.2, 0.91); P.add(win);
  const winRing = new THREE.Mesh(new THREE.RingGeometry(0.7, 0.95, 24), std('#2b2b2e'));
  winRing.position.set(8.4, 5.2, 0.915); P.add(winRing);

  smd(P, 5.4, 3.4, 'r', Math.PI / 2, 1.2, 0.7);
  smd(P, 5.4, 7.0, 'r', Math.PI / 2, 1.2, 0.7);
  smd(P, 11.6, 2.4, 'c', 0, 1.2, 0.7);
  on(P, 2.9, 1.3, 1.1, BLACK(), 4.3, 5.2, 0.0, 0.05);
  return g;
}

// ─── Batería LiPo 523450 con PCM y conector PH2.0 ───────────────────────────
// Se construye directamente en el espacio del visor (x largo 50, y ancho 34, z espesor 5,2)
export function buildBattery() {
  const g = new THREE.Group();
  const L = 50, W = 34, T = 5.2;

  const pouch = rbox(L, W, T, 2.4, std('#b6bdc9', { metalness: 0.55, roughness: 0.42 }));
  g.add(pouch);

  // Sello térmico en el extremo -x
  const seal = rbox(4.2, W - 4, 0.9, 0.3, std('#9aa3b2', { metalness: 0.5, roughness: 0.5 }));
  seal.position.set(-L / 2 - 1.6, 0, 0);
  g.add(seal);

  // Etiqueta
  const c = document.createElement('canvas');
  c.width = 1024; c.height = 700;
  const k = c.getContext('2d');
  k.fillStyle = '#f2f2f2'; k.fillRect(0, 0, c.width, c.height);
  k.fillStyle = '#1b6ec2'; k.fillRect(0, 0, c.width, 120);
  k.fillStyle = '#fff'; k.font = '700 78px Arial'; k.textAlign = 'left'; k.textBaseline = 'middle';
  k.fillText('Li-Po', 40, 62);
  k.fillStyle = '#111'; k.font = '700 120px Arial'; k.fillText('523450', 40, 260);
  k.font = '600 70px Arial'; k.fillText('3.7V  1000mAh', 40, 380); k.fillText('3.7Wh  Li-ion Polymer', 40, 470);
  k.font = '500 46px Arial'; k.fillStyle = '#444'; k.fillText('Rechargeable · con protección (PCM)', 40, 570);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  const label = new THREE.Mesh(new THREE.PlaneGeometry(L - 12, W - 8), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.6 }));
  label.position.set(-1, 0, T / 2 + 0.01);
  g.add(label);

  // PCM en el extremo +x con dos láminas de níquel
  const pcm = rbox(5.2, 11, 0.9, 0.2, std('#17803d', { roughness: 0.4 }));
  pcm.position.set(L / 2 + 1.6, 5, 0);
  g.add(pcm);
  const chip = rbox(2.2, 3.0, 0.6, 0.1, BLACK());
  chip.position.set(L / 2 + 1.6, 4.5, 0.7);
  g.add(chip);
  [2.4, 7.6].forEach((y) => {
    const tab = rbox(3.2, 3.0, 0.25, 0.05, METAL('#d5d9df'));
    tab.position.set(L / 2 - 0.4, y, 0);
    g.add(tab);
  });

  // Conector JST PH2.0 (2 pines hacia -y) y cables rojo / negro
  const conn = new THREE.Group();
  conn.add(rbox(6.0, 4.5, 4.4, 0.2, std('#efe9dc', { roughness: 0.6 })));
  [-1, 1].forEach((dx) => {
    const pin = rbox(0.5, 0.5, 1.2, 0.05, METAL('#d9a935'));
    pin.position.set(dx, 0, 2.2);
    conn.add(pin);
  });
  conn.rotation.x = Math.PI / 2; // pines hacia -y
  conn.position.set(L / 2 + 3.4, 14.4, 0.2);
  g.add(conn);
  const wire = (y0, dx, color) => {
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(L / 2 + 3.6, y0, 0.25),
      new THREE.Vector3(L / 2 + 6.4, (y0 + 12) / 2, 0.9),
      new THREE.Vector3(L / 2 + 3.4 + dx, 12.2, 0.4),
    ]);
    g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.36, 8), std(color, { roughness: 0.5 })));
  };
  wire(8.6, -1, '#d62828');
  wire(6.0, 1, '#101010');
  return g;
}

// ─── Motor de vibración plano (moneda 10 × 3 mm) con adhesivo y cables ──────
export function buildMotor() {
  const g = new THREE.Group();
  // eje en z; adhesivo contra la pared (z alto), cuerpo hacia -z
  const adhesive = new THREE.Mesh(new THREE.CylinderGeometry(5, 5, 0.3, 40), std('#f1e9c8', { roughness: 0.9 }));
  adhesive.rotation.x = Math.PI / 2;
  adhesive.position.z = 2.85;
  g.add(adhesive);
  const can = new THREE.Mesh(new THREE.CylinderGeometry(5, 5, 2.7, 48), METAL('#b8bec7'));
  can.rotation.x = Math.PI / 2;
  can.position.z = 1.35;
  g.add(can);
  const rim = new THREE.Mesh(new THREE.TorusGeometry(4.9, 0.12, 8, 48), METAL('#dfe3e8'));
  rim.position.z = 0.02;
  g.add(rim);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(4.6, 4.6, 0.12, 40), std('#1a1a1c'));
  base.rotation.x = Math.PI / 2;
  base.position.z = 0.0;
  g.add(base);
  // Cables
  const w = (dy, color) => {
    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(4.2, dy, 0.1),
      new THREE.Vector3(7.5, dy + dy * 0.3, 0.3),
      new THREE.Vector3(11, dy * 2.4, 0.5),
    ]);
    g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 16, 0.3, 8), std(color)));
    const tip = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 1.2, 8), METAL('#d9a935'));
    tip.rotation.z = Math.PI / 2; tip.position.set(11.6, dy * 2.4, 0.5);
    g.add(tip);
  };
  w(0.9, '#d62828'); w(-0.9, '#101010');
  return g;
}

// ─── Interruptor deslizante SS12D00 ─────────────────────────────────────────
export function buildSwitch() {
  const g = new THREE.Group();
  { const m = rbox(8.6, 3.8, 3.6, 0.15, METAL('#cfd3d9')); m.position.set(0, 0, 1.8); g.add(m); }
  { const m = rbox(8.0, 3.2, 0.4, 0.05, std('#16171a')); m.position.set(0, 0, 3.7); g.add(m); }
  // palanca que asoma por la ranura superior (+y es hacia la pared)
  const lever = rbox(3.4, 3.0, 1.5, 0.2, std('#202226', { roughness: 0.35 }));
  lever.position.set(0, 3.3, 1.8);
  g.add(lever);
  for (let i = -1; i <= 1; i++) {
    const rib = rbox(0.5, 1.0, 1.7, 0.05, std('#34373d'));
    rib.position.set(i * 1.0, 4.6, 1.8);
    g.add(rib);
  }
  // Patas
  [-2.5, 0, 2.5].forEach((x) => {
    const leg = rbox(0.5, 3.2, 0.3, 0.05, METAL('#d9a935'));
    leg.position.set(x, -3.0, 1.8);
    g.add(leg);
  });
  return g;
}

// ─── Antena FPC 40 × 20 mm con cable coaxial y U.FL ─────────────────────────
export function buildAntenna() {
  const g = new THREE.Group();
  const W = 40, H = 18;
  const c = document.createElement('canvas');
  c.width = 1600; c.height = 720;
  const k = c.getContext('2d');
  k.fillStyle = '#d9962a'; k.fillRect(0, 0, c.width, c.height);
  k.strokeStyle = '#8a5a12'; k.lineWidth = 12; k.lineJoin = 'round';
  k.beginPath();
  let x = 60;
  k.moveTo(x, 640);
  while (x < 1500) {
    k.lineTo(x, 120); x += 70; k.lineTo(x, 120); k.lineTo(x, 600); x += 70; k.lineTo(x, 600);
  }
  k.stroke();
  k.fillStyle = '#f2e1b0'; k.font = '600 44px Arial'; k.textAlign = 'right';
  k.fillText('2.4G FPC ANTENNA', 1540, 680);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  const fpc = new THREE.Mesh(new THREE.BoxGeometry(W, H, 0.22), [
    std('#c88a22'), std('#c88a22'), std('#c88a22'), std('#c88a22'),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.45, metalness: 0.15 }), std('#c88a22'),
  ]);
  g.add(fpc);
  return g;
}

// ─── Pulsador de hidratación: tact 6 × 6 × 4,3 mm + vástago + tapa de goma ──
// Convención local: +z apunta hacia el exterior (la pared de la carcasa); el origen es la cara inferior del
// cuerpo del pulsador. Las patas salen hacia -z. userData.press = grupo que se hunde al presionar.
export function buildButton() {
  const g = new THREE.Group();
  // Cuerpo del pulsador
  on(g, 6, 6, 3.4, BLACK(), 0, 0, 0, 0.35);
  on(g, 5.5, 5.5, 0.2, METAL('#b9bec6'), 0, 0, 3.4, 0.2);
  const act = new THREE.Mesh(new THREE.CylinderGeometry(1.75, 1.75, 0.7, 28), std('#26282d', { roughness: 0.35 }));
  act.rotation.x = Math.PI / 2;
  act.position.z = 3.95;
  g.add(act);
  // Patas (4, paso 6,5 × 4,5 mm)
  [-3.25, 3.25].forEach((x) => [-2.25, 2.25].forEach((y) => {
    const leg = rbox(0.55, 0.7, 3.0, 0.05, METAL('#d9a935'));
    leg.position.set(x, y, -1.5);
    g.add(leg);
    const top = rbox(0.55, 0.7, 0.35, 0.05, METAL('#d9a935'));
    top.position.set(x > 0 ? 3.0 : -3.0, y, 0.3);
    g.add(top);
  }));

  // Vástago + tapa (se hunden juntos)
  const press = new THREE.Group();
  const rod = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.6, 2.4, 24), std('#e8eaee', { roughness: 0.5 }));
  rod.rotation.x = Math.PI / 2;
  rod.position.z = 4.3 + 1.2;
  press.add(rod);
  const cap = rbox(10, 7, 1.5, 1.1, std('#0ea5e9', { roughness: 0.55 }));
  cap.position.z = 6.0 + 0.75;
  press.add(cap);
  // Pictograma de gota
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const k = c.getContext('2d');
  k.clearRect(0, 0, 256, 256);
  k.fillStyle = '#ffffff';
  k.beginPath();
  k.moveTo(128, 30);
  k.bezierCurveTo(128, 30, 52, 118, 52, 160);
  k.arc(128, 160, 76, Math.PI, 0, true);
  k.bezierCurveTo(204, 118, 128, 30, 128, 30);
  k.fill();
  k.fillStyle = '#0ea5e9';
  k.beginPath(); k.ellipse(104, 168, 14, 22, 0.5, 0, Math.PI * 2); k.fill();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  const icon = new THREE.Mesh(new THREE.PlaneGeometry(5, 5), new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.5, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  icon.position.z = 7.5 + 0.02;
  press.add(icon);
  g.add(press);
  g.userData.press = press;
  return g;
}
