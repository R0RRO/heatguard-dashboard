import { useState } from 'react';
import { Flame, LogIn } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { SITE } from '../data/seed';
import ClipLogo from './ClipLogo';
import ThemeToggle from './ThemeToggle';

// Inicio de sesión contra el servidor (server/index.js). El supervisor ve el panel; el trabajador, la app del clip.
export default function AuthScreen() {
  const { login, loginDemo } = useApp();
  const [usuario, setUsuario] = useState('');
  const [clave, setClave] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await login(usuario.trim(), clave); } catch (err) { setError(err.message); setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-navy-900 via-navy-800 to-navy-700 flex items-center justify-center p-4 relative">
      <ThemeToggle className="absolute top-4 right-4" />
      <form onSubmit={submit} className="bg-surface rounded-2xl shadow-2xl w-full max-w-sm p-7 space-y-5">
        <div className="text-center space-y-2">
          <div className="inline-flex bg-heat-500 rounded-2xl p-3"><Flame className="w-7 h-7 text-white" /></div>
          <h1 className="text-2xl font-extrabold text-ink">HEATGUARD <span className="text-heat-500">CLIP</span></h1>
          <p className="text-sm text-slate-500">Prevención del estrés térmico en obras · {SITE.name}</p>
          <ClipLogo active="normal" className="w-32 mx-auto" />
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600" htmlFor="usuario">Usuario</label>
          <input id="usuario" className="form-input mt-1" autoComplete="username" autoCapitalize="none" value={usuario} onChange={(e) => setUsuario(e.target.value)} required />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600" htmlFor="clave">Contraseña</label>
          <input id="clave" type="password" className="form-input mt-1" autoComplete="current-password" value={clave} onChange={(e) => setClave(e.target.value)} required />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}

        <button type="submit" disabled={busy} className="btn-primary w-full py-2.5"><LogIn className="w-4 h-4" />{busy ? 'Entrando…' : 'Entrar'}</button>
        <p className="text-[11px] text-center text-slate-400">
          <button type="button" onClick={loginDemo} className="underline cursor-pointer">Modo demo sin servidor</button>
        </p>
      </form>
    </div>
  );
}
