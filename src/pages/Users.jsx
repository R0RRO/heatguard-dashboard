import { useCallback, useEffect, useState } from 'react';
import { UserPlus, KeyRound, Trash2, Bluetooth } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { request } from '../lib/api';

const ROLE_LABEL = { admin: 'Administrador', supervisor: 'Supervisor', trabajador: 'Trabajador' };

// Usuarios y asignación de clips. Supervisor: asigna clips. Administrador: además crea, borra y cambia contraseñas.
export default function Users() {
  const { token, user, isAdmin, workers, usersVersion } = useApp();
  const [users, setUsers] = useState([]);
  const [msg, setMsg] = useState(null);
  const [form, setForm] = useState({ usuario: '', nombre: '', rol: 'trabajador', workerId: '', clave: '' });

  const load = useCallback(() => request('/api/users', { token }).then((d) => setUsers(d.users)).catch((e) => setMsg({ error: true, text: e.message })), [token]);
  useEffect(() => { load(); }, [load, usersVersion]);

  const run = async (fn, ok) => {
    try { await fn(); setMsg({ text: ok }); load(); } catch (e) { setMsg({ error: true, text: e.message }); }
  };
  const taken = Object.fromEntries(users.filter((u) => u.workerId).map((u) => [u.workerId, u.usuario]));
  const workerName = (id) => workers.find((w) => w.id === id);
  const options = (current) => workers.filter((w) => !taken[w.id] || w.id === current);

  const assign = (u, workerId) => run(
    () => request(`/api/users/${u.usuario}/clip`, { token, method: 'PUT', body: { workerId: workerId || null } }),
    workerId ? `Clip ${workerName(workerId)?.deviceId || workerId} asignado a ${u.name}` : `${u.name} quedó sin clip`,
  );
  const changePass = (u) => {
    const clave = window.prompt(`Nueva contraseña para ${u.usuario} (mínimo 10 caracteres)`);
    if (clave) run(() => request(`/api/users/${u.usuario}/clave`, { token, method: 'PUT', body: { clave } }), `Contraseña de ${u.usuario} cambiada`);
  };
  const remove = (u) => {
    if (window.confirm(`¿Borrar el usuario ${u.usuario}?`)) run(() => request(`/api/users/${u.usuario}`, { token, method: 'DELETE' }), `Usuario ${u.usuario} borrado`);
  };
  const create = (e) => {
    e.preventDefault();
    const body = { ...form, workerId: form.rol === 'trabajador' && form.workerId ? form.workerId : null };
    run(async () => { await request('/api/users', { token, method: 'POST', body }); setForm({ usuario: '', nombre: '', rol: 'trabajador', workerId: '', clave: '' }); }, `Usuario ${form.usuario} creado`);
  };

  return (
    <div className="page-layout">
      <h1 className="text-2xl font-extrabold text-ink">Usuarios</h1>
      {msg && <p className={`text-sm ${msg.error ? 'text-red-600' : 'text-emerald-600'}`}>{msg.text}</p>}

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line bg-surface-2/50">
            <tr><th className="th-c">Usuario</th><th className="th-c">Nombre</th><th className="th-c">Rol</th><th className="th-c">Clip asignado</th>{isAdmin && <th className="th-c" />}</tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.usuario} className="border-b border-slate-50">
                <td className="td-c font-mono">{u.usuario}</td>
                <td className="td-c">{u.name}</td>
                <td className="td-c">{ROLE_LABEL[u.role] || u.role}</td>
                <td className="td-c">
                  {u.role === 'trabajador' ? (
                    <label className="flex items-center gap-2">
                      <Bluetooth className="w-4 h-4 text-slate-400" />
                      <select className="form-select" value={u.workerId || ''} onChange={(e) => assign(u, e.target.value)}>
                        <option value="">Sin clip</option>
                        {options(u.workerId).map((w) => <option key={w.id} value={w.id}>{w.deviceId} · {w.id === u.workerId ? u.name : `puesto de ${w.name}`}</option>)}
                      </select>
                    </label>
                  ) : <span className="text-slate-400">—</span>}
                </td>
                {isAdmin && (
                  <td className="td-c">
                    <div className="flex gap-2 justify-end">
                      <button className="btn-secondary btn-sm" onClick={() => changePass(u)}><KeyRound className="w-3.5 h-3.5" />Contraseña</button>
                      {u.usuario !== user.usuario && <button className="btn-secondary btn-sm text-red-600" onClick={() => remove(u)}><Trash2 className="w-3.5 h-3.5" />Borrar</button>}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isAdmin && (
        <form onSubmit={create} className="card p-4 space-y-3">
          <h2 className="section-heading"><UserPlus className="w-4 h-4 text-ink-2" />Nuevo usuario</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <input className="form-input" placeholder="Usuario" autoCapitalize="none" value={form.usuario} onChange={(e) => setForm({ ...form, usuario: e.target.value })} required />
            <input className="form-input" placeholder="Nombre" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required />
            <select className="form-select" value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value })}>
              <option value="trabajador">Trabajador</option><option value="supervisor">Supervisor</option><option value="admin">Administrador</option>
            </select>
            {form.rol === 'trabajador' ? (
              <select className="form-select" value={form.workerId} onChange={(e) => setForm({ ...form, workerId: e.target.value })}>
                <option value="">Sin clip</option>
                {options(null).map((w) => <option key={w.id} value={w.id}>{w.deviceId} · puesto de {w.name}</option>)}
              </select>
            ) : <div />}
            <input className="form-input" type="password" placeholder="Contraseña (mín. 10)" autoComplete="new-password" value={form.clave} onChange={(e) => setForm({ ...form, clave: e.target.value })} required minLength={10} />
          </div>
          <button className="btn-primary"><UserPlus className="w-4 h-4" />Crear</button>
        </form>
      )}
    </div>
  );
}
