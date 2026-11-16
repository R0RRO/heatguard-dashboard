// Cambiar la contraseña de un usuario o crear uno nuevo.
//   node server/usuarios.js clave supervisor            (pide la nueva contraseña)
//   node server/usuarios.js nuevo trabajador2 "María Soto" trabajador w5
//   node server/usuarios.js lista
// Reinicia el servidor después de un cambio.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import readline from 'node:readline/promises';
import { fileURLToPath } from 'node:url';

const DATA = process.env.HG_DATA || path.join(path.dirname(fileURLToPath(import.meta.url)), 'data');
const f = path.join(DATA, 'usuarios.json');
const usuarios = fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : [];
const hash = (clave) => { const sal = crypto.randomBytes(16).toString('hex'); return { sal, hash: crypto.scryptSync(clave, sal, 32).toString('hex') }; };
const pedir = async (t) => { const rl = readline.createInterface({ input: process.stdin, output: process.stdout }); const r = await rl.question(t); rl.close(); return r; };
const guardar = () => { fs.mkdirSync(DATA, { recursive: true }); fs.writeFileSync(f, JSON.stringify(usuarios, null, 2)); };
const [accion, usuario, ...resto] = process.argv.slice(2);

if (accion === 'inicial') {
  // Crea los usuarios base que falten (admin, supervisor y trabajador Juan Pérez en w1). Contraseñas por variables de entorno.
  const base = [
    ['admin', 'Administrador', 'admin', null, process.env.HG_ADMIN_PASS],
    ['supervisor', 'Supervisor de obra', 'supervisor', null, process.env.HG_SUPERVISOR_PASS],
    ['trabajador', 'Juan Pérez', 'trabajador', 'w1', process.env.HG_TRABAJADOR_PASS],
  ];
  let creados = 0;
  for (const [usuario, nombre, rol, workerId, clave] of base) {
    if (usuarios.some((u) => u.usuario === usuario) || !clave) continue;
    usuarios.push({ usuario, nombre, rol, ...(workerId ? { workerId } : {}), ...hash(clave) });
    creados++;
    console.log('Creado:', usuario);
  }
  if (creados) guardar(); else console.log('No faltaba ningún usuario.');
} else if (accion === 'lista') {
  for (const u of usuarios) console.log(`${u.usuario}\t${u.rol}\t${u.nombre}${u.workerId ? `\t${u.workerId}` : ''}`);
} else if (accion === 'clave' && usuario) {
  const u = usuarios.find((x) => x.usuario === usuario);
  if (!u) { console.error('No existe ese usuario'); process.exit(1); }
  const clave = await pedir('Nueva contraseña (mínimo 10 caracteres): ');
  if (clave.length < 10) { console.error('Muy corta'); process.exit(1); }
  Object.assign(u, hash(clave)); guardar(); console.log('Listo. Reinicia el servidor.');
} else if (accion === 'nuevo' && usuario) {
  const [nombre, rol, workerId] = resto;
  if (!nombre || !['admin', 'supervisor', 'trabajador'].includes(rol)) { console.error('Uso: nuevo <usuario> "<nombre>" <admin|supervisor|trabajador> [w1]'); process.exit(1); }
  if (usuarios.some((x) => x.usuario === usuario)) { console.error('Ya existe'); process.exit(1); }
  const clave = await pedir('Contraseña (mínimo 10 caracteres): ');
  if (clave.length < 10) { console.error('Muy corta'); process.exit(1); }
  usuarios.push({ usuario, nombre, rol, ...(workerId ? { workerId } : {}), ...hash(clave) }); guardar(); console.log('Creado. Reinicia el servidor.');
} else {
  console.log('Uso: node server/usuarios.js inicial | lista | clave <usuario> | nuevo <usuario> "<nombre>" <rol> [workerId]');
}
