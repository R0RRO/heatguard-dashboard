// Cableado del clip según el documento técnico (sección 5: conexiones eléctricas).
// Todo en el espacio "front" del visor (x largo, y alto, z hacia el frente).
// Los cables que llegan a la batería se recalculan al explosionar.
import * as THREE from 'three';
import { partOffset } from './explodeLayout.js';

export const NETS = {
  bat_p: { label: 'BAT+ (batería → interruptor → XIAO)', color: '#dc2626' },
  bat_m: { label: 'BAT− / GND batería', color: '#0f172a' },
  v33: { label: '3V3', color: '#fb7185' },
  gnd: { label: 'GND', color: '#374151' },
  sda: { label: 'D4 · SDA (I2C)', color: '#8b5cf6' },
  scl: { label: 'D5 · SCL (I2C)', color: '#eab308' },
  led_r: { label: 'D2 · LED estado R (220 Ω)', color: '#ef4444' },
  led_g: { label: 'D3 · LED estado G (100 Ω)', color: '#22c55e' },
  led_b: { label: 'D6 · LED estado B (100 Ω)', color: '#38bdf8' },
  led2_r: { label: 'D10 · LED batería R (220 Ω)', color: '#fb923c' },
  motor: { label: 'D7 · motor (1 kΩ + 2N2222)', color: '#14b8a6' },
  coax: { label: 'Coaxial antena → u.FL', color: '#6b7280' },
  sense: { label: 'D1 · medición de batería (2 × 220 kΩ)', color: '#d97706' },
};

const V = (x, y, z) => new THREE.Vector3(x, y, z);
const EXPLODE_BATTERY_REL = -42;
const MARGIN = 1.5;
// Huella (xy) y rango z de cada pieza ensamblada, en el espacio del frente
export const FOOTPRINT = {
  xiao: { c: [26.5, -7.9], hw: 10.5, hh: 8.9, z0: 0.5, z1: 4.7 },
  mpu: { c: [-9.7, -9.5], hw: 10.5, hh: 8, z0: 3.2, z1: 6.5 },
  htu: { c: [-30, 0], hw: 6.75, hh: 5.25, z0: 2.4, z1: 4.5 },
  ant: { c: [-0.2, 7.05], hw: 20, hh: 9, z0: 6.2, z1: 6.75 },
  motor: { c: [26, 6.5], hw: 5, hh: 5, z0: 3.5, z1: 6.5 },
  sw: { c: [25.3, 17.3], hw: 4.3, hh: 3.6, z0: 0, z1: 3.9 },
  led1: { c: [5, -9], hw: 3, hh: 3, z0: -0.3, z1: 11 },
  led2: { c: [12.5, -9], hw: 3, hh: 3, z0: -0.3, z1: 11 },
}; // desplazamiento z de la batería respecto del frente por unidad de explosión

// Cable: tramos rectos con las esquinas redondeadas (sin las ondulaciones de una spline entre puntos muy desiguales)
function roundedPath(points, bend = 1.8) {
  const P = [points[0].clone()];
  for (let i = 1; i < points.length; i++) if (points[i].distanceTo(P[P.length - 1]) > 0.12) P.push(points[i].clone());
  const path = new THREE.CurvePath();
  const seg = (u, v) => { if (u.distanceTo(v) > 1e-4) path.add(new THREE.LineCurve3(u.clone(), v.clone())); };
  let cur = P[0].clone();
  for (let i = 1; i < P.length - 1; i++) {
    const a = P[i - 1], b = P[i], c = P[i + 1];
    const r = Math.min(bend, a.distanceTo(b) / 2, b.distanceTo(c) / 2);
    const p1 = b.clone().add(a.clone().sub(b).normalize().multiplyScalar(r));
    const p2 = b.clone().add(c.clone().sub(b).normalize().multiplyScalar(r));
    seg(cur, p1);
    path.add(new THREE.QuadraticBezierCurve3(p1, b.clone(), p2));
    cur = p2;
  }
  seg(cur, P[P.length - 1]);
  return path;
}

function tube(points, radius, color) {
  const curve = roundedPath(points);
  const segs = Math.min(500, Math.max(24, Math.ceil(curve.getLength() * 3)));
  const m = new THREE.Mesh(
    new THREE.TubeGeometry(curve, segs, radius, 8),
    new THREE.MeshStandardMaterial({ color, roughness: 0.45 }),
  );
  return { mesh: m, curve };
}

function resistor(curve, t, label) {
  const g = new THREE.Group();
  const p = curve.getPointAt(t);
  const tan = curve.getTangentAt(t);
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.75, 3.4, 14), new THREE.MeshStandardMaterial({ color: '#d8c39a', roughness: 0.7 }));
  const bandCol = { '220 Ω': ['#d00', '#d00', '#7a3f00'], '100 Ω': ['#7a3f00', '#111', '#7a3f00'], '1 kΩ': ['#7a3f00', '#111', '#d00'], '220 kΩ': ['#d00', '#d00', '#eab308'] }[label] || ['#d00', '#111', '#7a3f00'];
  g.add(body);
  [-0.9, 0, 0.9].forEach((y, i) => {
    const b = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.78, 0.35, 14), new THREE.MeshStandardMaterial({ color: bandCol[i], roughness: 0.6 }));
    b.position.y = y;
    g.add(b);
  });
  g.position.copy(p);
  g.quaternion.setFromUnitVectors(V(0, 1, 0), tan.normalize());
  return g;
}

export function buildWiring({ front, xiao, mpu, htu, motor, sw }) {
  front.updateMatrixWorld(true);
  const W = (obj, x, y, z) => obj.localToWorld(V(x, y, z));

  // Pads de la XIAO (7 por lado). Fila +y: D0…D6 (D0 junto al USB); fila −y: 5V, GND, 3V3, D10, D9, D8, D7.
  const xpad = (i, side, z = 0) => W(xiao, (i - 3) * 2.54 - 1.1, side * 8.45, z);
  const X = {
    D1: xpad(5, 1), D2: xpad(4, 1), D3: xpad(3, 1), D4: xpad(2, 1), D5: xpad(1, 1), D6: xpad(0, 1),
    GND: xpad(5, -1), V33: xpad(4, -1), D10: xpad(3, -1), D7: xpad(0, -1),
    BATP: W(xiao, 2.0, 4.5, -1.0), BATM: W(xiao, 5.0, 4.5, -1.0),
  };
  // GY-521: VCC, GND, SCL, SDA, XDA, XCL, AD0, INT (cabecera de 8, pitch 2,54)
  const mp = (i) => W(mpu, -8.1 + 2.54 * i, 6.5, 0);
  const M = { VCC: mp(0), GND: mp(1), SCL: mp(2), SDA: mp(3), AD0: mp(6) };
  // GY-21: VIN, GND, SCL, SDA
  const hp = (i) => W(htu, -5.55, -3.95 + 2.54 * i, 0);
  const H = { VIN: hp(0), GND: hp(1), SCL: hp(2), SDA: hp(3) };
  // Motor: cables rojo (+) y negro (−)
  const MO = { P: W(motor, 11.6, 2.16, 0.5), N: W(motor, 11.6, -2.16, 0.5) };
  // Interruptor: patas
  const S = { in: W(sw, 2.5, -3.9, 1.8), out: W(sw, 0, -3.9, 1.8) }; // punta de las patas (fuera del cuerpo)
  // LEDs de 5 mm (patas: R, común, G, B)
  const L1 = { R: V(3.1, -9, 0.2), C: V(4.37, -9, 0.2), G: V(5.63, -9, 0.2), B: V(6.9, -9, 0.2) };
  const L2 = { R: V(10.6, -9, 0.2), C: V(11.87, -9, 0.2) };
  // Conector JST de la batería (espacio de la batería, ya con su posición en el grupo)
  const J = { P: V(32.6, 11.9, -3.4), N: V(34.6, 11.9, -3.4) };

  const group = new THREE.Group();
  const off = new THREE.Vector3();
  const EXP = {};
  // Anclas base → con el desplazamiento de su pieza a la explosión actual
  const at = (key, v) => v.clone().add(partOffset(key, EXP.e, off));

  const render = (e) => {
    EXP.e = e;
    while (group.children.length) {
      const c = group.children.pop();
      c.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    }
    const Xp = {};
    Object.entries(X).forEach(([k, v]) => { Xp[k] = at('xiao', v); });
    const Mp = {};
    Object.entries(M).forEach(([k, v]) => { Mp[k] = at('mpu', v); });
    const Hp = {};
    Object.entries(H).forEach(([k, v]) => { Hp[k] = at('htu', v); });
    const MOp = { P: at('motor', MO.P), N: at('motor', MO.N) };
    const Sp = { in: at('sw', S.in), out: at('sw', S.out) };
    const L1p = {}; Object.entries(L1).forEach(([k, v]) => { L1p[k] = at('led1', v); });
    const L2p = {}; Object.entries(L2).forEach(([k, v]) => { L2p[k] = at('led2', v); });
    const Jp = { P: J.P.clone().add(V(0, 0, EXPLODE_BATTERY_REL * e)), N: J.N.clone().add(V(0, 0, EXPLODE_BATTERY_REL * e)) };
    const LEDS = [at('led1', V(5, -9, 0)), at('led2', V(12.5, -9, 0))];
    const R_AVOID = 3.9;
    let lane = 0;
    const smooth = (x0, x1, x) => { const t = Math.min(1, Math.max(0, (x - x0) / (x1 - x0))); return t * t * (3 - 2 * t); };
    const k = smooth(0.3, 0.6, e); // 0 = ensamblado (carril alto), 1 = despiezado (diagonal entre capas)

    // Obstáculos: huella xy y rango z de cada pieza con su desplazamiento actual
    const obstacles = Object.entries(FOOTPRINT).map(([key, fp]) => {
      const o = partOffset(key, e, new THREE.Vector3());
      return { key, cx: fp.c[0] + o.x, cy: fp.c[1] + o.y, hw: fp.hw + MARGIN, hh: fp.hh + MARGIN, z0: fp.z0 + o.z, z1: fp.z1 + o.z };
    });

    // Recorte segmento–rectángulo (Liang–Barsky): intervalo [t0, t1] dentro del rectángulo o null
    const clip = (p, q, o) => {
      let t0 = 0, t1 = 1;
      const d = [q.x - p.x, q.y - p.y];
      const lo = [o.cx - o.hw, o.cy - o.hh], hi = [o.cx + o.hw, o.cy + o.hh], pp = [p.x, p.y];
      for (let i = 0; i < 2; i++) {
        if (Math.abs(d[i]) < 1e-9) { if (pp[i] < lo[i] || pp[i] > hi[i]) return null; continue; }
        let ta = (lo[i] - pp[i]) / d[i], tb = (hi[i] - pp[i]) / d[i];
        if (ta > tb) [ta, tb] = [tb, ta];
        t0 = Math.max(t0, ta); t1 = Math.min(t1, tb);
        if (t0 >= t1) return null;
      }
      return [t0, t1];
    };

    // Ruta en xy entre s y t rodeando las piezas con las que el cable chocaría según su altura z
    const routeXY = (s2, t2, zf, excl) => {
      const inside = (p, o) => Math.abs(p.x - o.cx) < o.hw && Math.abs(p.y - o.cy) < o.hh;
      // Si un extremo cae en el margen de una pieza, para esa pieza se usa un margen mínimo; si cae dentro de ella, no cuenta
      const obs = obstacles.filter((o) => !excl.includes(o.key)).map((o) => {
        if (!inside(s2, o) && !inside(t2, o)) return o;
        const sm = { ...o, hw: o.hw - MARGIN + 0.45, hh: o.hh - MARGIN + 0.45 };
        return inside(s2, sm) || inside(t2, sm) ? null : sm;
      }).filter(Boolean);
      const blocked = (p, q) => obs.some((o) => {
        const c = clip(p, q, o);
        if (!c) return false;
        const zA = zf({ x: p.x + (q.x - p.x) * c[0], y: p.y + (q.y - p.y) * c[0] });
        const zB = zf({ x: p.x + (q.x - p.x) * c[1], y: p.y + (q.y - p.y) * c[1] });
        return Math.max(zA, zB) + 0.45 > o.z0 && Math.min(zA, zB) - 0.45 < o.z1;
      });
      if (!blocked(s2, t2)) return [];
      const nodes = [s2, t2];
      obs.forEach((o) => {
        [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(([sx, sy]) => nodes.push({ x: o.cx + sx * (o.hw + 0.35), y: o.cy + sy * (o.hh + 0.35) }));
      });
      const n = nodes.length;
      const dist = new Array(n).fill(Infinity);
      const prev = new Array(n).fill(-1);
      const done = new Array(n).fill(false);
      dist[0] = 0;
      for (let it = 0; it < n; it++) {
        let u = -1;
        for (let i = 0; i < n; i++) if (!done[i] && (u < 0 || dist[i] < dist[u])) u = i;
        if (u < 0 || dist[u] === Infinity) break;
        done[u] = true;
        if (u === 1) break;
        for (let v2 = 0; v2 < n; v2++) {
          if (done[v2]) continue;
          const w = Math.hypot(nodes[u].x - nodes[v2].x, nodes[u].y - nodes[v2].y);
          if (dist[u] + w < dist[v2] && !blocked(nodes[u], nodes[v2])) { dist[v2] = dist[u] + w; prev[v2] = u; }
        }
      }
      if (prev[1] < 0) return [];
      const path = [];
      for (let c = prev[1]; c > 0; c = prev[c]) path.unshift(nodes[c]);
      return path;
    };

    const b2s = (v) => `${v.x.toFixed(0)},${v.y.toFixed(0)}`;
    // Un cable: sale del pad a (sube un poco), viaja por la ruta hasta via y baja por tail hasta el destino.
    // ka / kb: piezas de los extremos (no cuentan como obstáculo).
    const wire = (net, a, via, tail, opts = {}) => {
      const { r = 0.27, res, resT = 0.5, ka = null, kb = null, za: zaIn, zb: zbIn, pre = [] } = opts;
      const hFix = 7.2 + (lane % 6) * 0.17;
      const laneOff = (lane % 6) * 0.17;
      lane++;
      const a0 = pre.length ? pre[pre.length - 1] : a;
      const za = zaIn ?? (hFix * (1 - k) + (a0.z + 3.0 + laneOff) * k);
      const zb = zbIn ?? (hFix * (1 - k) + (via.z + laneOff) * k);
      const dx = via.x - a0.x, dy = via.y - a0.y;
      const L2 = dx * dx + dy * dy || 1;
      const zf = (p) => za + (zb - za) * Math.min(1, Math.max(0, ((p.x - a0.x) * dx + (p.y - a0.y) * dy) / L2));
      const mid = routeXY(a0, via, zf, [ka, kb].filter(Boolean)).map((p) => V(p.x, p.y, zf(p)));
      const pts = [a.clone(), ...(pre.length ? pre : [V(a.x, a.y, a.z + 0.3)]), V(a0.x, a0.y, za), ...mid, V(via.x, via.y, zb), ...tail];
      const { mesh, curve } = tube(pts, r, NETS[net].color);
      mesh.userData.excl = [ka, kb];
      mesh.userData.net = net + '>' + (kb || '') + ':' + b2s(via);
      group.add(mesh);
      if (res) group.add(resistor(curve, resT, res));
    };

    // Destino estándar: pad b (se baja en vertical sobre él)
    const add = (net, a, b, opts = {}) => {
      const { led = null, ka, kb } = opts;
      const hFix = 7.2;
      const zbTop = hFix * (1 - k) + (b.z + 3.0) * k;
      if (led) {
        // Cables de LED: por detrás. Salen del pad al ras de la placa, viajan bajo la brida (z < 2,7)
        // y entran a la pata por el costado, nunca por delante del cuerpo del LED.
        const side = a.y < led.y ? -1 : 1;
        const out = V(b.x, led.y + side * (R_AVOID + 0.3 + (b.x % 2) * 0.01), 0);
        const exit = V(a.x, a.y + side * 1.6, a.z + 0.5);
        wire(net, a, V(out.x, out.y, b.z + 0.45), [V(b.x, b.y, b.z + 0.25)], { ...opts, ka, kb, pre: [exit], za: a.z + 0.6, zb: b.z + 0.45 });
      } else {
        wire(net, a, V(b.x, b.y, zbTop), [V(b.x, b.y, b.z + 0.3), b.clone()], { ...opts, ka, kb });
      }
    };

    // Alimentación 3V3
    add('v33', Xp.V33, Hp.VIN, { ka: 'xiao', kb: 'htu' });
    add('v33', Xp.V33, Mp.VCC, { ka: 'xiao', kb: 'mpu' });
    add('v33', Xp.V33, MOp.P, { r: 0.3, ka: 'xiao', kb: 'motor' });
    // Tierra
    add('gnd', Xp.GND, Hp.GND, { ka: 'xiao', kb: 'htu' });
    add('gnd', Xp.GND, Mp.GND, { ka: 'xiao', kb: 'mpu' });
    add('gnd', Xp.GND, Mp.AD0, { ka: 'xiao', kb: 'mpu' });
    add('gnd', Xp.GND, L1p.C, { led: LEDS[0], ka: 'xiao', kb: 'led1' });
    add('gnd', Xp.GND, L2p.C, { led: LEDS[1], ka: 'xiao', kb: 'led2' });
    // I2C
    add('sda', Xp.D4, Mp.SDA, { ka: 'xiao', kb: 'mpu' });
    add('sda', Xp.D4, Hp.SDA, { ka: 'xiao', kb: 'htu' });
    add('scl', Xp.D5, Mp.SCL, { ka: 'xiao', kb: 'mpu' });
    add('scl', Xp.D5, Hp.SCL, { ka: 'xiao', kb: 'htu' });
    // LEDs
    add('led_r', Xp.D2, L1p.R, { res: '220 Ω', resT: 0.3, led: LEDS[0], ka: 'xiao', kb: 'led1' });
    add('led_g', Xp.D3, L1p.G, { res: '100 Ω', resT: 0.3, led: LEDS[0], ka: 'xiao', kb: 'led1' });
    add('led_b', Xp.D6, L1p.B, { res: '100 Ω', resT: 0.3, led: LEDS[0], ka: 'xiao', kb: 'led1' });
    add('led2_r', Xp.D10, L2p.R, { res: '220 Ω', resT: 0.3, led: LEDS[1], ka: 'xiao', kb: 'led2' });
    // Motor (D7 → 1 kΩ → base del 2N2222; colector → cable negro del motor)
    add('motor', Xp.D7, MOp.N, { res: '1 kΩ', resT: 0.5, ka: 'xiao', kb: 'motor' });
    // Divisor de batería: BAT+ → 220 kΩ → D1 → 220 kΩ → GND
    add('sense', Sp.out, Xp.D1, { res: '220 kΩ', resT: 0.5, ka: 'sw', kb: 'xiao' });
    add('sense', Xp.D1, Xp.GND, { res: '220 kΩ', resT: 0.5, ka: 'xiao', kb: 'xiao' });
    // Los pads BAT+ / BAT− están en el REVERSO de la XIAO: los cables llegan por detrás (por debajo de la placa),
    // entrando desde el borde +y a ras del reverso, sin rodear la placa por delante.
    {
      const bp = Xp.BATP;
      wire('bat_p', Sp.out, V(bp.x, bp.y + 6, bp.z - 0.25), [V(bp.x, bp.y + 1.2, bp.z - 0.25), V(bp.x, bp.y, bp.z - 0.05)], { r: 0.4, ka: 'sw', kb: 'xiao', za: Sp.out.z + 1.2, zb: bp.z - 0.25 });
    }
    // Cables de la batería (JST → interruptor y BAT−)
    {
      const a = Jp.P;
      wire('bat_p', a, V(Sp.in.x + 2.6, Sp.in.y + 0.2, Sp.in.z), [Sp.in.clone()], { r: 0.4, kb: 'sw', za: a.z + 3, zb: Sp.in.z });
    }
    {
      const a = Jp.N;
      const bm = Xp.BATM;
      wire('bat_m', a, V(bm.x, bm.y + 6, bm.z - 0.25), [V(bm.x, bm.y + 1.2, bm.z - 0.25), V(bm.x, bm.y, bm.z - 0.05)], { r: 0.4, kb: 'xiao', za: a.z + 2, zb: bm.z - 0.25 });
    }
    // Coaxial de la antena al u.FL de la XIAO
    {
      const pa = at('ant', V(9, -1.9, 6.0));
      const pu = at('xiao', V(17.7, -10.5, 2.5));
      wire('coax', pa, V(pu.x + 0.4, pu.y - 0.6, pu.z + 1.2), [pu], { r: 0.5, ka: 'ant', kb: 'xiao', za: pa.z - 0.5, zb: pu.z + 1.2 });
    }
  };

  let last = null;
  const update = (e) => {
    const k = Math.round(e * 100);
    if (k === last) return;
    last = k;
    render(k / 100);
  };
  update(0);
  return { group, update };
}
