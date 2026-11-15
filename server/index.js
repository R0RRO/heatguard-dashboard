// Servidor del HeatGuard Clip: entrega el dashboard, maneja el inicio de sesión y reenvía en tiempo real los
// datos de los clips reales (que suben los celulares de los trabajadores) y los comandos del supervisor.
// Node 20+ y sin dependencias. Uso: node server/index.js   (variables: PORT, HOST, HG_DATA, ver README)
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';
import { createState, step, orderPause, cancelPause, pressButton, ackAlert, resolveAlert, setProfile } from '../src/lib/simulation.js';
import { displayStatus } from '../src/lib/risk.js';
import { ZONES } from '../src/data/seed.js';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = process.env.HG_DIST || path.join(RAIZ, 'dist');
const DATA = process.env.HG_DATA || path.join(RAIZ, 'server', 'data');
const PORT = Number(process.env.PORT || 8787);
const HOST = process.env.HOST || '127.0.0.1';   // detrás de Tailscale Funnel: solo escucha localmente
const TOKEN_HORAS = { supervisor: 12, trabajador: 24 * 14 };   // el celular del trabajador sube datos todo el día
const MAX_BODY = 16 * 1024;

fs.mkdirSync(DATA, { recursive: true });
const archivo = (n) => path.join(DATA, n);
const leerJSON = (n, def) => { try { return JSON.parse(fs.readFileSync(archivo(n), 'utf8')); } catch { return def; } };
const guardarJSON = (n, v) => { const tmp = archivo(n + '.tmp'); fs.writeFileSync(tmp, JSON.stringify(v, null, 2)); fs.renameSync(tmp, archivo(n)); };
const log = (...a) => console.log(new Date().toISOString(), ...a);

// ───────── Usuarios ─────────
// Se crean la primera vez con las contraseñas de las variables HG_SUPERVISOR_PASS y HG_TRABAJADOR_PASS.
// Para cambiarlas después: node server/usuarios.js
export const hashClave = (clave, sal = crypto.randomBytes(16).toString('hex')) =>
  ({ sal, hash: crypto.scryptSync(clave, sal, 32).toString('hex') });
const claveCorrecta = (u, clave) => {
  const h = crypto.scryptSync(String(clave), u.sal, 32);
  return crypto.timingSafeEqual(h, Buffer.from(u.hash, 'hex'));
};

function cargarUsuarios() {
  let usuarios = leerJSON('usuarios.json', null);
  if (usuarios) return usuarios;
  const sup = process.env.HG_SUPERVISOR_PASS;
  const tra = process.env.HG_TRABAJADOR_PASS;
  if (!sup || !tra) {
    console.error('Faltan usuarios: define HG_SUPERVISOR_PASS y HG_TRABAJADOR_PASS la primera vez (o crea usuarios con server/usuarios.js).');
    process.exit(1);
  }
  usuarios = [
    { usuario: 'supervisor', nombre: 'Supervisor de obra', rol: 'supervisor', ...hashClave(sup) },
    { usuario: 'trabajador', nombre: 'Juan Pérez', rol: 'trabajador', workerId: 'w1', ...hashClave(tra) },
  ];
  guardarJSON('usuarios.json', usuarios);
  log('Usuarios creados: supervisor, trabajador');
  return usuarios;
}
const usuarios = cargarUsuarios();
const nombres = () => Object.fromEntries(usuarios.filter((u) => u.workerId).map((u) => [u.workerId, u.nombre]));
const publico = (u) => ({ usuario: u.usuario, name: u.nombre, role: u.rol, workerId: u.workerId || null });

// Sesiones (se guardan en disco para que un reinicio del servidor no corte la app del trabajador)
const sesiones = new Map(Object.entries(leerJSON('sesiones.json', {})).filter(([, v]) => v.exp > Date.now()));
let guardarSes = null;
const guardarSesiones = () => { clearTimeout(guardarSes); guardarSes = setTimeout(() => guardarJSON('sesiones.json', Object.fromEntries(sesiones)), 500); };
function sesion(req, url) {
  const auth = req.headers.authorization || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : url.searchParams.get('token');
  const s = token && sesiones.get(token);
  if (!s || s.exp < Date.now()) { if (s) { sesiones.delete(token); guardarSesiones(); } return null; }
  return { ...s, token };
}

// Límite de intentos de inicio de sesión por IP (el servidor queda público)
const intentos = new Map();
function puedeIntentar(ip) {
  const ahora = Date.now();
  const lista = (intentos.get(ip) || []).filter((t) => ahora - t < 10 * 60000);
  intentos.set(ip, lista);
  return lista.length < 10;
}

// ───────── Estado compartido ─────────
const DEF_CONFIG = { loadLimit: 120, tiredPct: 70, pauseMinutes: 15, autoPause: true, confirmMinutes: 5, simResponds: true };
let estado = leerJSON('estado.json', {});
estado = { config: { ...DEF_CONFIG, ...(estado.config || {}) }, profiles: estado.profiles || {} };
const guardarEstado = () => guardarJSON('estado.json', estado);
const vivos = {};              // workerId → { msg, at, link, device, appAt }
const pendientes = {};         // workerId → comandos para el celular que aún no se entregan

// ───────── Tiempo real (Server-Sent Events) ─────────
const clientes = new Set();    // { res, out, rol, workerId, lite }
function enviarTexto(c, texto) { c.out.write(texto); if (c.out !== c.res) c.out.flush(); }
function enviar(c, evento, datos) { enviarTexto(c, `event: ${evento}\ndata: ${JSON.stringify(datos)}\n\n`); }
function aSupervisores(evento, datos) { for (const c of clientes) if (c.rol === 'supervisor') enviar(c, evento, datos); }
function aTrabajador(workerId, evento, datos) {
  let entregado = false;
  for (const c of clientes) if (c.rol === 'trabajador' && c.workerId === workerId) { enviar(c, evento, datos); entregado = true; }
  return entregado;
}
setInterval(() => { for (const c of clientes) enviarTexto(c, ': latido\n\n'); }, 20000);
setInterval(() => {   // un celular que deja de enviar aparece sin señal (el panel también lo detecta)
  const ahora = Date.now();
  for (const [id, v] of Object.entries(vivos)) {
    if (v.link !== 'off' && ahora - v.appAt > 30000) { v.link = 'off'; aSupervisores('live', { workerId: id, ...v }); }
  }
}, 5000);

// Comando para el clip real de un trabajador: se entrega a su celular (o queda pendiente hasta que se conecte)
function reenviarComando(workerId, cmd, arg = 0) {
  const c = { cmd, arg, at: Date.now() };
  if (aTrabajador(workerId, 'command', c)) return true;
  (pendientes[workerId] ||= []).push(c);
  pendientes[workerId] = pendientes[workerId].slice(-20);
  return false;
}
const COMANDO = { pauseRequest: 2, identify: 5, cancelPauseRequest: 6 };
const enVivo = (id) => vivos[id] && vivos[id].link !== 'off';

// ───────── Simulación de la cuadrilla (la misma para todos los paneles y la app) ─────────
// Los trabajadores con un clip real enlazado usan sus lecturas; el resto es simulado (src/lib/simulation.js).
const sim = { state: null, running: true, speed: 1, heatOffset: 0, tickAt: {}, ticks: 0 };
function nuevaSim() {
  let st = createState(estado.config, sim.heatOffset);
  for (const [id, p] of Object.entries(estado.profiles)) st = setProfile(st, id, p);
  sim.state = st; sim.ticks = 0;
}
nuevaSim();
const simCtl = () => ({ running: sim.running, speed: sim.speed, heatOffset: sim.heatOffset });
const sinHistoria = (w) => { const { history, ...resto } = w; return { ...resto, points: history.slice(-sim.speed) }; };
function simDelta(toasts) {
  const st = sim.state;
  return { clock: st.clock, workers: st.workers.map(sinHistoria), alerts: st.alerts.slice(0, 60), events: st.events, spare: st.spare,
    nextAlertId: st.nextAlertId, sitePoints: st.siteHistory.slice(-sim.speed), toasts, ctl: simCtl() };
}
const simCompleta = () => ({ ...sim.state, alerts: sim.state.alerts.slice(0, 60), ctl: simCtl() });
const r1 = (x) => (Number.isFinite(x) ? Math.round(x * 10) / 10 : null);
function simLite() {   // versión condensada para la app Android
  const st = sim.state;
  const zona = Object.fromEntries(ZONES.map((z) => [z.id, z.name]));
  return {
    clock: st.clock, ctl: simCtl(), pauseMinutes: estado.config.pauseMinutes,
    workers: st.workers.map((w) => ({
      id: w.id, name: w.name, trade: w.trade, crew: w.crew, zone: zona[w.zoneId] || '', status: displayStatus(w),
      load: Math.round(w.load), ok: !!w.env.ok, t: r1(w.env.t), rh: Math.round(w.env.rh ?? 0), hi: r1(w.env.hi),
      mov: Math.round((w.activity || 0) * 100), bat: Math.round(w.battery ?? 0), sig: Number.isFinite(w.signal) ? Math.round(w.signal) : null,
      real: w.source === 'clip', req: !!w.pauseReq, reqSup: w.pauseReq?.source === 'supervisor',
      pauseMin: w.resting && w.pauseStart != null ? st.clock - w.pauseStart : null, pauses: w.pausesToday,
    })),
    alerts: st.alerts.filter((a) => a.status === 'activa').slice(0, 10).map((a) => ({ id: a.id, level: a.level, name: a.workerName, reason: a.reason })),
  };
}
function emitirSim(toasts = []) {
  let delta = null, lite = null;
  for (const c of clientes) {
    if (c.rol !== 'supervisor') continue;
    if (c.lite) enviar(c, 'simlite', lite ||= simLite());
    else enviar(c, 'sim', delta ||= simDelta(toasts));
  }
}
setInterval(() => {
  if (!sim.running) return;
  const ahora = Date.now();
  const live = [];
  for (const [id, v] of Object.entries(vivos)) {
    if (v.link === 'off') { delete sim.tickAt[id]; continue; }
    live.push({ workerId: id, msg: v.msg, linked: !!v.msg && ahora - v.at < 8000, dtMin: sim.tickAt[id] ? (ahora - sim.tickAt[id]) / 60000 : 0 });
    sim.tickAt[id] = ahora;
  }
  let toasts = [];
  for (let i = 0; i < sim.speed; i++) {
    const r = step(sim.state, estado.config, sim.heatOffset, i === 0 ? live : live.map((l) => ({ ...l, dtMin: 0 })));
    sim.state = r.state; toasts = toasts.concat(r.toasts);
  }
  sim.ticks += sim.speed;
  emitirSim(sim.ticks > 6 ? toasts : []);
}, 1500);

// ───────── HTTP ─────────
function json(res, code, datos) {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  res.end(JSON.stringify(datos));
}
function leerCuerpo(req) {
  return new Promise((ok, mal) => {
    let tam = 0; const partes = [];
    req.on('data', (d) => { tam += d.length; if (tam > MAX_BODY) { mal(new Error('demasiado grande')); req.destroy(); } else partes.push(d); });
    req.on('end', () => { try { ok(partes.length ? JSON.parse(Buffer.concat(partes).toString('utf8')) : {}); } catch { mal(new Error('JSON inválido')); } });
    req.on('error', mal);
  });
}
const num = (v, a, b) => typeof v === 'number' && Number.isFinite(v) && v >= a && v <= b;
const workerIdValido = (id) => typeof id === 'string' && /^w\d{1,3}$/.test(id);

// Revisión básica de una lectura que sube el celular (el contrato completo está en src/lib/telemetry.js)
function lecturaValida(m) {
  return m && typeof m === 'object' && num(m.v, 1, 9) && num(m.seq, 0, 65535) && m.env && m.motion && m.battery
    && num(m.load, 0, 255) && num(m.state, 0, 4) && num(m.battery.pct, 0, 100) && num(m.motion.index, 0, 100)
    && (!m.env.ok || (num(m.env.tempC, -20, 70) && num(m.env.rhPct, 0, 100)));
}

const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json',
  '.stl': 'model/stl', '.ico': 'image/x-icon', '.woff2': 'font/woff2' };
function archivoEstatico(req, res, url) {
  let ruta = decodeURIComponent(url.pathname);
  let f = path.normalize(path.join(DIST, ruta));
  if (!f.startsWith(DIST)) { res.writeHead(400); return res.end(); }
  if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(DIST, 'index.html');   // aplicación de una página
  if (!fs.existsSync(f)) { res.writeHead(500); return res.end('Falta compilar el dashboard: npm run build'); }
  const ext = path.extname(f);
  res.writeHead(200, {
    'content-type': TIPOS[ext] || 'application/octet-stream',
    'cache-control': ruta.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
  });
  fs.createReadStream(f).pipe(res);
}

async function api(req, res, url) {
  const ruta = url.pathname;
  const ip = String(req.headers['x-forwarded-for'] || req.socket.remoteAddress || '').split(',')[0].trim();

  if (ruta === '/api/login' && req.method === 'POST') {
    if (!puedeIntentar(ip)) return json(res, 429, { error: 'Demasiados intentos. Espera unos minutos.' });
    const { usuario, clave } = await leerCuerpo(req);
    const u = usuarios.find((x) => x.usuario === String(usuario || '').trim().toLowerCase());
    intentos.get(ip).push(Date.now());
    if (!u || !claveCorrecta(u, clave || '')) return json(res, 401, { error: 'Usuario o contraseña incorrectos.' });
    const token = crypto.randomBytes(32).toString('hex');
    sesiones.set(token, { usuario: u.usuario, rol: u.rol, workerId: u.workerId || null, exp: Date.now() + (TOKEN_HORAS[u.rol] || 12) * 3600000 });
    guardarSesiones();
    log('Entró', u.usuario, 'desde', ip);
    return json(res, 200, { token, user: publico(u) });
  }

  const s = sesion(req, url);
  if (!s) return json(res, 401, { error: 'Sesión vencida. Vuelve a entrar.' });
  const u = usuarios.find((x) => x.usuario === s.usuario);
  const esSup = s.rol === 'supervisor';

  if (ruta === '/api/logout' && req.method === 'POST') { sesiones.delete(s.token); guardarSesiones(); return json(res, 200, { ok: true }); }
  if (ruta === '/api/me') return json(res, 200, { user: publico(u) });
  if (ruta === '/api/state') return json(res, 200, { config: estado.config, profiles: estado.profiles, live: vivos, names: nombres() });

  if (ruta === '/api/stream') {
    const gzip = /\bgzip\b/.test(req.headers['accept-encoding'] || '');
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive', 'x-accel-buffering': 'no',
      ...(gzip ? { 'content-encoding': 'gzip' } : {}) });
    const out = gzip ? zlib.createGzip({ flush: zlib.constants.Z_SYNC_FLUSH }) : res;
    if (gzip) out.pipe(res);
    const workerId = workerIdValido(url.searchParams.get('workerId')) ? url.searchParams.get('workerId') : s.workerId;
    const c = { res, out, rol: s.rol, workerId, lite: url.searchParams.get('lite') === '1' };
    clientes.add(c);
    enviar(c, 'state', { config: estado.config, profiles: estado.profiles, live: vivos, names: nombres() });
    if (esSup) enviar(c, c.lite ? 'simlite' : 'simfull', c.lite ? simLite() : simCompleta());
    if (!esSup && workerId) for (const cmd of pendientes[workerId]?.splice(0) || []) enviar(c, 'command', cmd);
    req.on('close', () => { clientes.delete(c); if (gzip) out.end(); });
    return undefined;
  }

  if (ruta === '/api/config' && req.method === 'PUT') {
    if (!esSup) return json(res, 403, { error: 'Solo el supervisor' });
    const b = await leerCuerpo(req);
    const c = { ...estado.config };
    if (num(b.loadLimit, 30, 250)) c.loadLimit = Math.round(b.loadLimit);
    if (num(b.tiredPct, 30, 95)) c.tiredPct = Math.round(b.tiredPct);
    if (num(b.pauseMinutes, 5, 60)) c.pauseMinutes = Math.round(b.pauseMinutes);
    if (num(b.confirmMinutes, 1, 60)) c.confirmMinutes = Math.round(b.confirmMinutes);
    if (typeof b.autoPause === 'boolean') c.autoPause = b.autoPause;
    if (typeof b.simResponds === 'boolean') c.simResponds = b.simResponds;
    estado.config = c; guardarEstado();
    aSupervisores('config', c);
    for (const cl of clientes) if (cl.rol === 'trabajador') enviar(cl, 'config', c);
    return json(res, 200, c);
  }

  const mPerfil = ruta.match(/^\/api\/profile\/(w\d{1,3})$/);
  if (mPerfil && req.method === 'PUT') {
    if (!esSup) return json(res, 403, { error: 'Solo el supervisor' });
    const { heightCm, weightKg } = await leerCuerpo(req);
    if (!num(heightCm, 120, 230) || !num(weightKg, 35, 250)) return json(res, 400, { error: 'Altura o peso fuera de rango' });
    estado.profiles[mPerfil[1]] = { heightCm, weightKg }; guardarEstado();
    sim.state = setProfile(sim.state, mPerfil[1], { heightCm, weightKg });
    aSupervisores('profile', { workerId: mPerfil[1], heightCm, weightKg });
    aTrabajador(mPerfil[1], 'profile', { workerId: mPerfil[1], heightCm, weightKg });
    return json(res, 200, { ok: true });
  }

  if (ruta === '/api/command' && req.method === 'POST') {
    if (!esSup) return json(res, 403, { error: 'Solo el supervisor' });
    const { workerId, cmd, arg = 0 } = await leerCuerpo(req);
    if (!workerIdValido(workerId) || !num(cmd, 1, 20) || !num(arg, 0, 255)) return json(res, 400, { error: 'Comando inválido' });
    return json(res, 200, { ok: true, entregado: reenviarComando(workerId, cmd, arg) });
  }

  // Acciones sobre la simulación compartida (y el clip real, si el trabajador tiene uno enlazado)
  if (ruta === '/api/sim' && req.method === 'POST') {
    if (!esSup) return json(res, 403, { error: 'Solo el supervisor' });
    const b = await leerCuerpo(req);
    const id = b.workerId;
    const th = estado.config;
    const existe = workerIdValido(id) && sim.state.workers.some((w) => w.id === id);
    switch (b.action) {
      case 'orderPause': {
        if (!existe) return json(res, 400, { error: 'Trabajador inválido' });
        const min = num(b.minutes, 5, 60) ? Math.round(b.minutes) : th.pauseMinutes;
        sim.state = orderPause(sim.state, id, min);
        if (enVivo(id)) reenviarComando(id, COMANDO.pauseRequest, min);
        break;
      }
      case 'cancelPause':
        if (!existe) return json(res, 400, { error: 'Trabajador inválido' });
        sim.state = cancelPause(sim.state, id, th);
        if (enVivo(id)) reenviarComando(id, COMANDO.cancelPauseRequest);
        break;
      case 'identify':
        if (!existe || !enVivo(id)) return json(res, 400, { error: 'Ese trabajador no tiene un clip real enlazado' });
        reenviarComando(id, COMANDO.identify);
        break;
      case 'pressButton':
        if (!existe) return json(res, 400, { error: 'Trabajador inválido' });
        if (enVivo(id)) return json(res, 400, { error: 'Con clip real, la pausa se marca con el botón físico' });
        sim.state = pressButton(sim.state, id, th);
        break;
      case 'ackAlert': sim.state = ackAlert(sim.state, Number(b.alertId)); break;
      case 'resolveAlert': sim.state = resolveAlert(sim.state, Number(b.alertId)); break;
      case 'reset': nuevaSim(); break;
      case 'control':
        if (typeof b.running === 'boolean') sim.running = b.running;
        if (num(b.speed, 1, 10)) sim.speed = Math.round(b.speed);
        if (num(b.heatOffset, -6, 10)) sim.heatOffset = Math.round(b.heatOffset);
        break;
      default: return json(res, 400, { error: 'Acción desconocida' });
    }
    if (b.action === 'reset') for (const c of clientes) if (c.rol === 'supervisor') enviar(c, c.lite ? 'simlite' : 'simfull', c.lite ? simLite() : simCompleta());
    else emitirSim();
    return json(res, 200, { ok: true });
  }

  // Celular del trabajador: estado del enlace con el clip y lecturas
  if (ruta === '/api/link' && req.method === 'POST') {
    const { workerId, link, device } = await leerCuerpo(req);
    if (!workerIdValido(workerId) || !['connecting', 'connected', 'reconnecting', 'off'].includes(link)) return json(res, 400, { error: 'Datos inválidos' });
    const v = (vivos[workerId] ||= { msg: null, at: 0 });
    Object.assign(v, { link, device: String(device || '').slice(0, 40), appAt: Date.now(), by: s.usuario });
    aSupervisores('live', { workerId, ...v });
    log('Clip', workerId, link, 'por', s.usuario);
    return json(res, 200, { ok: true });
  }
  if (ruta === '/api/telemetry' && req.method === 'POST') {
    const { workerId, msg } = await leerCuerpo(req);
    if (!workerIdValido(workerId) || !lecturaValida(msg)) return json(res, 400, { error: 'Lectura inválida' });
    const v = (vivos[workerId] ||= {});
    Object.assign(v, { msg, at: Date.now(), appAt: Date.now(), link: 'connected', by: s.usuario });
    aSupervisores('live', { workerId, ...v });
    return json(res, 200, { ok: true });
  }

  return json(res, 404, { error: 'No existe' });
}

const servidor = http.createServer(async (req, res) => {
  res.setHeader('x-content-type-options', 'nosniff');
  res.setHeader('referrer-policy', 'same-origin');
  res.setHeader('x-frame-options', 'DENY');
  const url = new URL(req.url, 'http://local');
  try {
    if (url.pathname.startsWith('/api/')) return await api(req, res, url);
    return archivoEstatico(req, res, url);
  } catch (e) {
    if (!res.headersSent) json(res, 400, { error: e.message });
    else res.end();
  }
});
servidor.listen(PORT, HOST, () => log(`HeatGuard en http://${HOST}:${PORT} (datos en ${DATA})`));
