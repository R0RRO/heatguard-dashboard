// Servidor del HeatGuard Clip: entrega el dashboard, maneja el inicio de sesión y reenvía en tiempo real los
// datos de los clips reales (que suben los celulares de los trabajadores) y los comandos del supervisor.
// Node 20+ y sin dependencias. Uso: node server/index.js   (variables: PORT, HOST, HG_DATA, ver README)
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';
import { createState, advance, applyWbgt, SPEED_MIN, SPEED_MAX, orderPause, cancelPause, pressButton, ackAlert, resolveAlert, setProfile } from '../src/lib/simulation.js';
import { displayStatus } from '../src/lib/risk.js';
import { ZONES, WORKER_SEEDS, SITE } from '../src/data/seed.js';

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
    ...(process.env.HG_ADMIN_PASS ? [{ usuario: 'admin', nombre: 'Administrador', rol: 'admin', ...hashClave(process.env.HG_ADMIN_PASS) }] : []),
    { usuario: 'supervisor', nombre: 'Supervisor de obra', rol: 'supervisor', ...hashClave(sup) },
    { usuario: 'trabajador', nombre: 'Juan Pérez', rol: 'trabajador', workerId: 'w1', ...hashClave(tra) },
  ];
  guardarJSON('usuarios.json', usuarios);
  log('Usuarios creados: supervisor, trabajador');
  return usuarios;
}
const usuarios = cargarUsuarios();
const guardarUsuarios = () => guardarJSON('usuarios.json', usuarios);
// Roles: admin (todo), supervisor (monitorea, pide pausas y asigna clips), trabajador (su clip)
const ROLES = ['admin', 'supervisor', 'trabajador'];
const esMonitor = (rol) => rol === 'admin' || rol === 'supervisor';
const nombres = () => Object.fromEntries(usuarios.filter((u) => u.rol === 'trabajador' && u.workerId).map((u) => [u.workerId, u.nombre]));
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
  const u = usuarios.find((x) => x.usuario === s.usuario);   // el rol y el clip asignado se leen al día
  if (!u) { sesiones.delete(token); guardarSesiones(); return null; }
  return { ...s, rol: u.rol, workerId: u.workerId || null, token };
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
function aSupervisores(evento, datos) { for (const c of clientes) if (esMonitor(c.rol)) enviar(c, evento, datos); }
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

const avisarUsuarios = () => { aSupervisores('users', { users: usuarios.map(publico), names: nombres() }); emitirSim(); };

// Comando para el clip real de un trabajador: se entrega a su celular (o queda pendiente hasta que se conecte)
function reenviarComando(workerId, cmd, arg = 0) {
  const c = { cmd, arg, at: Date.now() };
  if (aTrabajador(workerId, 'command', c)) return true;
  (pendientes[workerId] ||= []).push(c);
  pendientes[workerId] = pendientes[workerId].slice(-20);
  return false;
}
const COMANDO = { pauseRequest: 2, identify: 5, cancelPauseRequest: 6, wbgtLevel: 11 };
const enVivo = (id) => vivos[id] && vivos[id].link !== 'off';

// ───────── Simulación de la cuadrilla (la misma para todos los paneles y la app) ─────────
// Los trabajadores con un clip real enlazado usan sus lecturas; el resto es simulado (src/lib/simulation.js).
const sim = { state: null, running: true, speed: 1, heatOffset: 0, tickAt: {}, ticks: 0, acc: 0, lastSteps: 1 };
function nuevaSim() {
  let st = createState(estado.config, sim.heatOffset);
  for (const [id, p] of Object.entries(estado.profiles)) st = setProfile(st, id, p);
  sim.state = st; sim.ticks = 0;
  aplicarNombres();
}
// El trabajador de la simulación toma el nombre del usuario que tiene ese clip asignado
function aplicarNombres() {
  if (!sim.state) return;
  const asignado = Object.fromEntries(usuarios.filter((u) => u.rol === 'trabajador' && u.workerId).map((u) => [u.workerId, u.nombre]));
  const semilla = Object.fromEntries(WORKER_SEEDS.map((w) => [w.id, w.name]));
  const usados = new Set(Object.values(asignado));
  // un puesto sin usuario cuyo nombre de ejemplo coincide con un usuario real se marca, para no ver dos personas iguales
  const nombre = (w) => asignado[w.id] || (usados.has(semilla[w.id]) ? `${semilla[w.id]} (simulado)` : semilla[w.id]) || w.name;
  sim.state = { ...sim.state, workers: sim.state.workers.map((w) => ({ ...w, name: nombre(w) })) };
}
nuevaSim();
const simCtl = () => ({ running: sim.running, speed: sim.speed, heatOffset: sim.heatOffset, wbgt: wb.status });
const sinHistoria = (w) => { const { history, ...resto } = w; return { ...resto, points: sim.lastSteps ? history.slice(-sim.lastSteps) : [] }; };
function simDelta(toasts) {
  const st = sim.state;
  return { clock: st.clock, workers: st.workers.map(sinHistoria), alerts: st.alerts.slice(0, 60), events: st.events, spare: st.spare,
    nextAlertId: st.nextAlertId, sitePoints: sim.lastSteps ? st.siteHistory.slice(-sim.lastSteps) : [], toasts, ctl: simCtl() };
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
      wbgt: w.wbgt ? r1(w.wbgt.c) : null, wbgtLevel: w.wbgt ? w.wbgt.level : null, wbgtLabel: w.wbgt ? w.wbgt.label : null,
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
    if (!esMonitor(c.rol)) continue;
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
  // velocidad fraccionaria: se acumula y se avanzan los minutos enteros que correspondan
  sim.acc += sim.speed;
  const pasos = Math.floor(sim.acc + 1e-9);
  sim.acc -= pasos;
  const r = advance(sim.state, estado.config, sim.heatOffset, live, pasos);
  sim.state = r.state;
  sim.lastSteps = pasos;
  sim.ticks += pasos;
  actualizarWbgt();
  if (pasos === 0 && !live.length) return;   // nada cambió en este intervalo
  emitirSim(sim.ticks > 6 ? r.toasts : []);
}, 1500);

// ───────── WBGT estimado (motor Python, motor_termico_python/integracion/servicio_wbgt.py) ─────────
// En cada ciclo se envía la temperatura y humedad de toda la cuadrilla; el WBGT que vuelve define el factor
// de calor de la exposición (simulados aquí; clips reales con el comando 11). Sin servicio o sin meteorología,
// se usa la sensación térmica como respaldo.
const WBGT_URL = process.env.HG_WBGT_URL || 'http://127.0.0.1:8790';
const WBGT_KEY = process.env.HG_WBGT_KEY || '';
const wb = { status: WBGT_KEY ? 'iniciando' : 'desactivado', byId: {}, okAt: 0, pending: false, sent: {} };

// Fecha y hora de Santiago para un minuto del reloj simulado (hoy), en ISO UTC
function horaSantiago(minutosDia) {
  const ahora = new Date();
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Santiago', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(ahora).map((x) => [x.type, x.value]));
  const localComoUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
  const offsetMin = Math.round((localComoUtc - ahora.getTime()) / 60000);   // ej. −180 en verano
  const m = ((minutosDia % 1440) + 1440) % 1440;
  return new Date(Date.UTC(+p.year, +p.month - 1, +p.day) + (m - offsetMin) * 60000).toISOString();
}

async function actualizarWbgt() {
  if (!WBGT_KEY || wb.pending || !sim.state) return;
  wb.pending = true;
  const ahoraIso = new Date().toISOString();
  const simIso = horaSantiago(sim.state.clock);
  const items = sim.state.workers.filter((w) => Number.isFinite(w.env?.t) && Number.isFinite(w.env?.rh)).map((w) => ({
    id: w.id, tempC: Math.round(w.env.t * 10) / 10, rhPct: Math.round(w.env.rh),
    timestamp: w.source === 'clip' ? ahoraIso : simIso,   // el clip real usa la hora real; la simulación, su reloj
  }));
  try {
    const res = await fetch(`${WBGT_URL}/v1/wbgt/lote`, {
      method: 'POST', headers: { 'content-type': 'application/json', 'x-api-key': WBGT_KEY },
      body: JSON.stringify({ lat: SITE.center[0], lon: SITE.center[1], items }), signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    const byId = {};
    for (const it of d.items || []) {
      if (it.status === 'ok') byId[it.id] = { c: it.wbgtC, level: it.level, label: it.label, solarWm2: it.solarWm2, windMs: it.windMs };
    }
    const antes = wb.status;
    wb.status = d.meteo?.status === 'ok' ? 'ok' : 'sin_meteorologia';
    if (antes !== wb.status) log('WBGT:', wb.status, d.meteo?.detail || '');
    wb.byId = byId;
    if (Object.keys(byId).length) wb.okAt = Date.now();
  } catch (e) {
    if (wb.status !== 'caido') log('WBGT: servicio no disponible,', e.message);
    wb.status = 'caido';
  } finally {
    wb.pending = false;
  }
  if (Date.now() - wb.okAt > 120000) wb.byId = {};   // datos viejos: vuelve la sensación térmica
  sim.state = applyWbgt(sim.state, wb.byId);
  enviarNivelAClips();
}

// Clips reales: el firmware usa el nivel WBGT que le llega (comando 11, arg = nivel + 1; 0 = sensación térmica)
function enviarNivelAClips() {
  const ahora = Date.now();
  for (const [id, v] of Object.entries(vivos)) {
    if (v.link === 'off') continue;
    const dato = wb.byId[id];
    const arg = dato ? dato.level + 1 : 0;
    const prev = wb.sent[id];
    if (prev && prev.arg === arg && ahora - prev.at < 60000) continue;
    if (aTrabajador(id, 'command', { cmd: COMANDO.wbgtLevel, arg, at: ahora })) {
      wb.sent[id] = { arg, at: ahora };
      aTrabajador(id, 'heat', dato ? { source: 'wbgt', wbgtC: dato.c, level: dato.level, label: dato.label } : { source: 'hi' });
    }
  }
}

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
  const esSup = esMonitor(s.rol);
  const esAdmin = s.rol === 'admin';
  const soloAdmin = () => json(res, 403, { error: 'Solo el administrador' });

  if (ruta === '/api/logout' && req.method === 'POST') { sesiones.delete(s.token); guardarSesiones(); return json(res, 200, { ok: true }); }
  if (ruta === '/api/me') return json(res, 200, { user: publico(u) });
  if (ruta === '/api/state') return json(res, 200, { config: estado.config, profiles: estado.profiles, live: vivos, names: nombres() });

  if (ruta === '/api/stream') {
    const gzip = /\bgzip\b/.test(req.headers['accept-encoding'] || '');
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive', 'x-accel-buffering': 'no',
      ...(gzip ? { 'content-encoding': 'gzip' } : {}) });
    const out = gzip ? zlib.createGzip({ flush: zlib.constants.Z_SYNC_FLUSH }) : res;
    if (gzip) out.pipe(res);
    const workerId = s.rol === 'trabajador' ? s.workerId : null;
    const c = { res, out, rol: s.rol, usuario: s.usuario, workerId, lite: url.searchParams.get('lite') === '1' };
    clientes.add(c);
    enviar(c, 'state', { config: estado.config, profiles: estado.profiles, live: vivos, names: nombres() });
    if (esSup) enviar(c, c.lite ? 'simlite' : 'simfull', c.lite ? simLite() : simCompleta());
    if (!esSup && workerId) for (const cmd of pendientes[workerId]?.splice(0) || []) enviar(c, 'command', cmd);
    req.on('close', () => { clientes.delete(c); if (gzip) out.end(); });
    return undefined;
  }

  if (ruta === '/api/config' && req.method === 'PUT') {
    if (!esAdmin) return soloAdmin();
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
    if (!esAdmin) return soloAdmin();
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
      case 'reset': nuevaSim(); sim.state = applyWbgt(sim.state, wb.byId); break;
      case 'control':
        // controles de la simulación (para demostrar el sistema): supervisor y admin
        if (typeof b.running === 'boolean') sim.running = b.running;
        if (num(b.speed, SPEED_MIN, SPEED_MAX)) { sim.speed = Math.round(b.speed * 1000) / 1000; sim.acc = 0; }
        if (num(b.heatOffset, -6, 10)) sim.heatOffset = Math.round(b.heatOffset);
        break;
      default: return json(res, 400, { error: 'Acción desconocida' });
    }
    if (b.action === 'reset') {
      for (const c of clientes) if (esMonitor(c.rol)) enviar(c, c.lite ? 'simlite' : 'simfull', c.lite ? simLite() : simCompleta());
    } else {
      emitirSim();
    }
    return json(res, 200, { ok: true });
  }

  // ───────── Usuarios y asignación de clips ─────────
  if (ruta === '/api/users' && req.method === 'GET') {
    if (!esSup) return json(res, 403, { error: 'Sin permiso' });
    return json(res, 200, { users: usuarios.map(publico) });
  }
  if (ruta === '/api/users' && req.method === 'POST') {
    if (!esAdmin) return soloAdmin();
    const b = await leerCuerpo(req);
    const usuario = String(b.usuario || '').trim().toLowerCase();
    const nombre = String(b.nombre || '').trim().slice(0, 60);
    if (!/^[a-z0-9._-]{3,30}$/.test(usuario)) return json(res, 400, { error: 'Usuario: 3 a 30 letras, números, punto, guion' });
    if (usuarios.some((u) => u.usuario === usuario)) return json(res, 400, { error: 'Ese usuario ya existe' });
    if (!nombre) return json(res, 400, { error: 'Falta el nombre' });
    if (!ROLES.includes(b.rol)) return json(res, 400, { error: 'Rol inválido' });
    if (typeof b.clave !== 'string' || b.clave.length < 10) return json(res, 400, { error: 'La contraseña debe tener al menos 10 caracteres' });
    const workerId = b.rol === 'trabajador' && workerIdValido(b.workerId) ? b.workerId : null;
    if (workerId && usuarios.some((u) => u.workerId === workerId)) return json(res, 400, { error: 'Ese clip ya está asignado a otro usuario' });
    usuarios.push({ usuario, nombre, rol: b.rol, ...(workerId ? { workerId } : {}), ...hashClave(b.clave) });
    guardarUsuarios(); aplicarNombres(); avisarUsuarios();
    log('Usuario creado', usuario, b.rol, 'por', s.usuario);
    return json(res, 200, { ok: true });
  }
  const mUser = ruta.match(/^\/api\/users\/([a-z0-9._-]{1,30})(\/clave|\/clip)?$/);
  if (mUser) {
    const u = usuarios.find((x) => x.usuario === mUser[1]);
    if (!u) return json(res, 404, { error: 'No existe ese usuario' });
    if (mUser[2] === '/clip' && req.method === 'PUT') {
      if (!esSup) return json(res, 403, { error: 'Sin permiso' });
      if (u.rol !== 'trabajador') return json(res, 400, { error: 'Solo se asignan clips a trabajadores' });
      const { workerId } = await leerCuerpo(req);
      if (workerId !== null && !workerIdValido(workerId)) return json(res, 400, { error: 'Clip inválido' });
      const otro = workerId && usuarios.find((x) => x.workerId === workerId && x !== u);
      if (otro) return json(res, 400, { error: `Ese clip ya está asignado a ${otro.nombre}` });
      const antes = u.workerId;
      if (workerId) u.workerId = workerId; else delete u.workerId;
      guardarUsuarios(); aplicarNombres();
      if (antes && antes !== workerId && vivos[antes]) { vivos[antes].link = 'off'; aSupervisores('live', { workerId: antes, ...vivos[antes] }); }
      // la app del trabajador se reconecta y queda con el clip nuevo
      for (const c of clientes) if (c.usuario === u.usuario) c.res.end();
      avisarUsuarios();
      log('Clip', workerId || 'ninguno', 'asignado a', u.usuario, 'por', s.usuario);
      return json(res, 200, { ok: true });
    }
    if (mUser[2] === '/clave' && req.method === 'PUT') {
      if (!esAdmin) return soloAdmin();
      const { clave } = await leerCuerpo(req);
      if (typeof clave !== 'string' || clave.length < 10) return json(res, 400, { error: 'La contraseña debe tener al menos 10 caracteres' });
      Object.assign(u, hashClave(clave));
      for (const [t, ses] of sesiones) if (ses.usuario === u.usuario && t !== s.token) sesiones.delete(t);   // cierra sus otras sesiones
      guardarUsuarios(); guardarSesiones();
      return json(res, 200, { ok: true });
    }
    if (!mUser[2] && req.method === 'DELETE') {
      if (!esAdmin) return soloAdmin();
      if (u.usuario === s.usuario) return json(res, 400, { error: 'No puedes borrar tu propio usuario' });
      if (u.rol === 'admin' && usuarios.filter((x) => x.rol === 'admin').length === 1) return json(res, 400, { error: 'Debe quedar al menos un administrador' });
      usuarios.splice(usuarios.indexOf(u), 1);
      for (const [t, ses] of sesiones) if (ses.usuario === u.usuario) sesiones.delete(t);
      for (const c of clientes) if (c.usuario === u.usuario) c.res.end();
      guardarUsuarios(); guardarSesiones(); aplicarNombres(); avisarUsuarios();
      log('Usuario borrado', u.usuario, 'por', s.usuario);
      return json(res, 200, { ok: true });
    }
  }

  // Celular del trabajador: estado del enlace con el clip y lecturas
  if (ruta === '/api/link' && req.method === 'POST') {
    const b = await leerCuerpo(req);
    const { link, device } = b;
    const workerId = s.rol === 'trabajador' ? s.workerId : b.workerId;   // el trabajador solo informa su propio clip
    if (!workerIdValido(workerId) || !['connecting', 'connected', 'reconnecting', 'off'].includes(link)) return json(res, 400, { error: 'Datos inválidos' });
    const v = (vivos[workerId] ||= { msg: null, at: 0 });
    Object.assign(v, { link, device: String(device || '').slice(0, 40), appAt: Date.now(), by: s.usuario });
    aSupervisores('live', { workerId, ...v });
    log('Clip', workerId, link, 'por', s.usuario);
    return json(res, 200, { ok: true });
  }
  if (ruta === '/api/telemetry' && req.method === 'POST') {
    const b = await leerCuerpo(req);
    const { msg } = b;
    const workerId = s.rol === 'trabajador' ? s.workerId : b.workerId;
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
