import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { toCreasedNormals } from 'three/addons/utils/BufferGeometryUtils.js';
import { HOTSPOTS, LED_STATES, SIGNALS } from '../data/product';
import { buildWiring } from '../lib/wiring';
import { partOffset, HOTSPOT_PART } from '../lib/explodeLayout';
import { buildXiao, buildMpu, buildHtu, buildBattery, buildMotor, buildSwitch, buildAntenna, buildButton } from '../lib/componentModels';

const SHELL = '#d3d9e2';
const ACCESSORY = '#4b5668';

// Los STL vienen orientados para imprimir. Cada función los lleva al espacio del
// visor: x = largo, y = alto, z = hacia el frente.
const PARTS = [
  { key: 'tapa',  file: 'HeatGuard_Tapa_Frontal.stl', group: 'front', color: SHELL,     map: (x, y, z) => [x, -y, 8.5 - z] },
  { key: 'base',  file: 'HeatGuard_Base_Trasera.stl', group: 'base',  color: SHELL,     map: (x, y, z) => [x, y, z - 8.5] },
  { key: 'clip',  file: 'HeatGuard_Clip_Chaleco.stl', group: 'acc',   color: ACCESSORY, map: (x, y, z) => [z - 37, -x, -(y + 12.6)] },
  { key: 'casco', file: 'HeatGuard_Placa_Casco.stl',  group: 'acc',   color: ACCESSORY, map: (x, y, z) => [x, -y, -(z + 8.5)] },
];

const EXPLODE = { front: 34, base: -26, battery: 18, acc: -52 };

function glowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.35, 'rgba(255,255,255,.35)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

// Componentes internos (ver lib/componentModels.js), colocados según el documento técnico.
// Espacio del visor: x largo, y alto, z hacia el frente.
function buildComponents() {
  const front = new THREE.Group();
  const battery = new THREE.Group();

  const xiao = buildXiao();
  xiao.position.set(26.5, -7.9, 1.5);

  const mpu = buildMpu();
  mpu.rotation.y = Math.PI;           // componentes hacia el interior
  mpu.position.set(-9.7, -9.5, 4.9);

  const htu = buildHtu();
  htu.position.set(-30, 0, 3.5);      // sensor mirando a la rejilla

  const antenna = buildAntenna();
  antenna.position.set(-0.2, 7.05, 6.35);

  const motor = buildMotor();
  motor.position.set(26, 6.5, 3.5);

  const sw = buildSwitch();
  sw.position.set(25.3, 16.1, 0);

  // Pulsador de hidratación en la pared superior (+y): vástago y tapa asoman hacia afuera
  const btn = buildButton();
  btn.rotation.x = -Math.PI / 2;      // +z local → +y (hacia la pared)
  btn.position.set(9, 14.0, 2.5);

  // Cada pieza va en su propio grupo para poder separarla al explosionar
  const parts = {};
  Object.entries({ xiao, mpu, htu, ant: antenna, motor, sw, btn }).forEach(([k, o]) => {
    const w = new THREE.Group();
    w.add(o);
    front.add(w);
    parts[k] = w;
  });
  const wiring = buildWiring({ front, xiao, mpu, htu, motor, sw, btn });
  front.add(wiring.group);

  const bat = buildBattery();
  bat.position.set(5.2, 0, -3.6);
  battery.add(bat);
  return { front, battery, wiring, parts, buttonPress: btn.userData.press };
}

export default function ClipViewer({
  ledState = 'normal', batteryLow = false, vibrate = false, explode = 0, interior = false, wires = false, reminder = false, pressKey = 0,
  accessory = 'none', autoRotate = true, showLabels = true, selected = null, onSelect, resetKey = 0,
}) {
  const mountRef = useRef(null);
  const overlayRef = useRef(null);
  const propsRef = useRef({});
  const apiRef = useRef(null);
  const dotRefs = useRef({});
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    propsRef.current = { ledState, batteryLow, vibrate, explode, interior, wires, reminder, pressKey, accessory, autoRotate, showLabels, selected };
  });

  useEffect(() => {
    const mount = mountRef.current;
    let cancelled = false;
    let raf = 0;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    mount.appendChild(renderer.domElement);
    renderer.domElement.style.display = 'block';

    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTex;
    scene.environmentIntensity = 0.5;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8794a8, 0.25));
    const sun = new THREE.DirectionalLight(0xffffff, 1.9);
    sun.position.set(60, 100, 90);
    scene.add(sun);

    const camera = new THREE.PerspectiveCamera(32, 1, 1, 1000);
    camera.position.set(78, 44, 128);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = 70;
    controls.maxDistance = 320;
    controls.autoRotateSpeed = 1.1;
    controls.saveState();

    // Sombra de contacto
    const shadow = new THREE.Mesh(
      new THREE.PlaneGeometry(190, 190),
      new THREE.MeshBasicMaterial({ map: glowTexture(), color: 0x000000, transparent: true, opacity: 0.22, depthWrite: false }),
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = -34;
    scene.add(shadow);

    const root = new THREE.Group();
    scene.add(root);
    const groups = { front: new THREE.Group(), base: new THREE.Group(), battery: new THREE.Group(), acc: new THREE.Group() };
    groups.base.add(groups.battery);
    root.add(groups.front, groups.base, groups.acc);

    const { front: compFront, battery: compBattery, wiring, parts, buttonPress } = buildComponents();
    parts.led1 = new THREE.Group();
    parts.led2 = new THREE.Group();
    groups.front.add(parts.led1, parts.led2);
    groups.front.add(compFront);
    groups.battery.add(compBattery);
    const compMeshes = [compFront, compBattery];

    // LEDs
    const ledMat = new THREE.MeshStandardMaterial({ color: '#334155', emissive: '#000000', roughness: 0.25, transparent: true, opacity: 0.95 });
    const batMat = new THREE.MeshStandardMaterial({ color: '#334155', emissive: '#000000', roughness: 0.25, transparent: true, opacity: 0.95 });
    const domeGeo = new THREE.SphereGeometry(2.5, 24, 16);
    const led1 = new THREE.Mesh(domeGeo, ledMat);
    led1.position.set(5, -9, 8.5);
    const led2 = new THREE.Mesh(domeGeo, batMat);
    led2.position.set(12.5, -9, 8.5);
    const glowTex = glowTexture();
    const mkGlow = (x) => {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: '#ffffff', transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0 }));
      s.position.set(x, -9, 11.5);
      s.scale.setScalar(10);
      return s;
    };
    const glow1 = mkGlow(5);
    const glow2 = mkGlow(12.5);
    // Cuerpo del LED de 5 mm (epoxi difuso), brida y patas
    const ledBodyGeo = new THREE.CylinderGeometry(2.5, 2.5, 5.2, 28);
    const flangeGeo = new THREE.CylinderGeometry(3.0, 3.0, 0.9, 28);
    const legMat = new THREE.MeshStandardMaterial({ color: '#c9ced6', metalness: 1, roughness: 0.3 });
    [[led1, ledMat, parts.led1], [led2, batMat, parts.led2]].forEach(([dome, mat, lg]) => {
      const body = new THREE.Mesh(ledBodyGeo, mat);
      body.rotation.x = Math.PI / 2;
      body.position.set(dome.position.x, dome.position.y, 8.5 - 2.6);
      const flange = new THREE.Mesh(flangeGeo, mat);
      flange.rotation.x = Math.PI / 2;
      flange.position.set(dome.position.x, dome.position.y, 8.5 - 5.3);
      lg.add(body, flange);
      [-1.9, -0.63, 0.63, 1.9].forEach((dx, i) => {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.5, 3.2), legMat);
        leg.position.set(dome.position.x + dx, dome.position.y + (i === 1 ? 0 : 0.0), 8.5 - 7.2);
        lg.add(leg);
      });
    });
    parts.led1.add(led1, glow1);
    parts.led2.add(led2, glow2);

    // Anclas de los puntos de interés
    const anchors = HOTSPOTS.map((h) => {
      const a = new THREE.Object3D();
      a.position.set(...h.pos);
      groups[h.group].add(a);
      return a;
    });

    const shellMats = [];
    const meshes = {};
    const loader = new STLLoader();
    Promise.all(PARTS.map((p) => new Promise((resolve, reject) => {
      loader.load(`/models/${p.file}`, (geo) => {
        const pos = geo.attributes.position;
        for (let i = 0; i < pos.count; i++) {
          const [x, y, z] = p.map(pos.getX(i), pos.getY(i), pos.getZ(i));
          pos.setXYZ(i, x, y, z);
        }
        geo.deleteAttribute('normal');
        const g2 = toCreasedNormals(geo, Math.PI / 5);
        const mat = new THREE.MeshStandardMaterial({ color: p.color, roughness: p.group === 'acc' ? 0.7 : 0.5, metalness: 0.02 });
        if (p.group !== 'acc') shellMats.push(mat);
        const mesh = new THREE.Mesh(g2, mat);
        groups[p.group].add(mesh);
        meshes[p.key] = mesh;
        resolve();
      }, undefined, reject);
    }))).then(() => { if (!cancelled) setStatus('ready'); }).catch(() => { if (!cancelled) setStatus('error'); });

    // Tamaño
    const resize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.zoom = Math.min(1, Math.max(0.5, w / h / 1.5)); // en vertical, aleja el modelo
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    const state = { pressKey: propsRef.current.pressKey, ackT0: -99, explode: 0, shellOpacity: 1, transparentOn: false };
    const v = new THREE.Vector3();
    const n = new THREE.Vector3();
    const toCam = new THREE.Vector3();
    const clock = new THREE.Clock();
    const tmpOff = new THREE.Vector3();

    const animate = () => {
      raf = requestAnimationFrame(animate);
      const t = clock.getElapsedTime();
      const p = propsRef.current;

      controls.autoRotate = !!p.autoRotate;
      controls.update();

      // Explosión suavizada
      state.explode += ((p.explode ?? 0) - state.explode) * 0.12;
      const e = state.explode;
      groups.front.position.z = EXPLODE.front * e;
      groups.base.position.z = EXPLODE.base * e;
      groups.battery.position.z = EXPLODE.battery * e;
      groups.acc.position.z = EXPLODE.acc * e;
      // Cada componente se separa individualmente; sus puntos de interés y cables lo siguen
      Object.entries(parts).forEach(([k, g]) => partOffset(k, e, g.position));
      HOTSPOTS.forEach((hs, i) => {
        const k = HOTSPOT_PART[hs.id];
        if (k) anchors[i].position.set(hs.pos[0], hs.pos[1], hs.pos[2]).add(partOffset(k, e, tmpOff));
      });

      // Accesorio
      if (meshes.clip) meshes.clip.visible = p.accessory === 'clip';
      if (meshes.casco) meshes.casco.visible = p.accessory === 'casco';

      // Transparencia de la carcasa (vista interior)
      const targetOp = p.interior ? 0.16 : 1;
      state.shellOpacity += (targetOp - state.shellOpacity) * 0.15;
      const trans = state.shellOpacity < 0.99;
      shellMats.forEach((m) => {
        m.opacity = state.shellOpacity;
        if (m.transparent !== trans) { m.transparent = trans; m.depthWrite = !trans; m.needsUpdate = true; }
      });
      // Las piezas internas se renderizan siempre: se ven por el puerto USB-C y la rejilla de ventilación
      compMeshes.forEach((c) => { c.visible = true; });
      wiring.group.visible = !!p.wires;
      if (p.wires) wiring.update(e);

      // Botón de hidratación: al presionar, la tapa se hunde y el clip confirma (LED verde ×2 + vibración corta)
      if (p.pressKey !== state.pressKey) { state.pressKey = p.pressKey; state.ackT0 = t; }
      const dtAck = t - state.ackT0;
      const acking = dtAck >= 0 && dtAck < 1.5;
      const pressDepth = dtAck >= 0 && dtAck < 0.5 ? Math.sin((dtAck / 0.5) * Math.PI) : 0;
      buttonPress.position.z = -0.85 * pressDepth;
      const ackOn = acking && dtAck > 0.45 && (dtAck % 0.5) < 0.28;

      // LEDs (prioridad: confirmación > recordatorio > estado)
      let cfg = LED_STATES[p.ledState] || LED_STATES.normal;
      let blink = p.ledState === 'alerta' ? (Math.sin(t * 9) > 0 ? 1 : 0.25) : 1;
      if (acking) { cfg = { color: SIGNALS.registro.color }; blink = ackOn ? 1 : 0.1; }
      else if (p.reminder) { cfg = { color: SIGNALS.recordatorio.color }; blink = 0.55 + 0.45 * Math.sin(t * 3.2); }
      ledMat.emissive.set(cfg.color);
      ledMat.emissiveIntensity = 2.2 * blink;
      ledMat.color.set(cfg.color);
      glow1.material.color.set(cfg.color);
      glow1.material.opacity = 0.85 * blink;
      glow1.scale.setScalar(9 + 2 * blink);
      const low = !!p.batteryLow;
      batMat.emissive.set(low ? '#ef4444' : '#000000');
      batMat.emissiveIntensity = low ? 2 : 0;
      batMat.color.set(low ? '#ef4444' : '#334155');
      glow2.material.color.set('#ef4444');
      glow2.material.opacity = low ? 0.8 : 0;

      // Vibración
      const remBuzz = p.reminder && !acking && (t % 1.6) < 0.35;
      const ackBuzz = acking && dtAck > 0.45 && dtAck < 0.8;
      if (p.vibrate || remBuzz || ackBuzz) root.position.set(Math.sin(t * 95) * 0.45, Math.cos(t * 80) * 0.35, 0);
      else root.position.set(0, 0, 0);

      // Puntos de interés proyectados sobre el canvas
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      HOTSPOTS.forEach((hs, i) => {
        const el = dotRefs.current[hs.id];
        if (!el) return;
        anchors[i].getWorldPosition(v);
        let visible = p.showLabels;
        if (hs.interior) visible = visible && !!p.interior;
        else if (hs.normal) {
          n.set(...hs.normal);
          toCam.copy(camera.position).sub(v).normalize();
          visible = visible && n.dot(toCam) > 0.12;
        }
        v.project(camera);
        if (v.z > 1) visible = false;
        el.style.opacity = visible ? '1' : '0';
        el.style.pointerEvents = visible ? 'auto' : 'none';
        el.style.transform = `translate(${(v.x * 0.5 + 0.5) * w - 11}px, ${(-v.y * 0.5 + 0.5) * h - 11}px)`;
      });

      renderer.render(scene, camera);
    };
    animate();

    apiRef.current = { controls };

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => { m.map?.dispose?.(); m.dispose(); });
      });
      envTex.dispose();
      pmrem.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
      apiRef.current = null;
    };
  }, []);

  useEffect(() => { apiRef.current?.controls.reset(); }, [resetKey]);

  return (
    <div className="relative w-full h-full">
      <div ref={mountRef} className="absolute inset-0" />
      <div ref={overlayRef} className="absolute inset-0 overflow-hidden pointer-events-none">
        {HOTSPOTS.map((h) => (
          <button
            key={h.id}
            ref={(el) => { dotRefs.current[h.id] = el; }}
            onClick={() => onSelect?.(h.id)}
            title={h.title}
            style={{ opacity: 0, transition: 'opacity .2s' }}
            className={`absolute top-0 left-0 w-[22px] h-[22px] rounded-full text-[11px] font-bold flex items-center justify-center cursor-pointer border-2 shadow-md ${selected === h.id ? 'bg-heat-500 text-white border-white scale-110' : 'bg-navy-900/85 text-white border-white/80 hover:bg-heat-500'}`}
          >
            {h.n}
          </button>
        ))}
      </div>
      {status !== 'ready' && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
          {status === 'loading' ? 'Cargando modelo 3D…' : 'No se pudo cargar el modelo 3D.'}
        </div>
      )}
    </div>
  );
}
