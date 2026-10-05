import { useState } from 'react';
import { Flame, HardHat, ClipboardCheck, ShieldCheck } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { SITE } from '../data/seed';
import ClipLogo from './ClipLogo';
import ThemeToggle from './ThemeToggle';

const ROLES = [
  { id: 'supervisor', label: 'Supervisor de obra', desc: 'Monitorea cuadrillas y ordena pausas.', icon: HardHat },
  { id: 'prevencionista', label: 'Prevencionista', desc: 'Ajusta umbrales y revisa alertas.', icon: ClipboardCheck },
  { id: 'admin', label: 'Administrador', desc: 'Gestiona dispositivos y configuración.', icon: ShieldCheck },
];

export default function AuthScreen() {
  const { login } = useApp();
  const [name, setName] = useState('');
  const [role, setRole] = useState('supervisor');

  const submit = (e) => {
    e.preventDefault();
    login({ name: name.trim() || 'Usuario demo', role });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-navy-900 via-navy-800 to-navy-700 flex items-center justify-center p-4 relative">
      <ThemeToggle className="absolute top-4 right-4" />
      <form onSubmit={submit} className="bg-surface rounded-2xl shadow-2xl w-full max-w-md p-7 space-y-5">
        <div className="text-center space-y-2">
          <div className="inline-flex bg-heat-500 rounded-2xl p-3"><Flame className="w-7 h-7 text-white" /></div>
          <h1 className="text-2xl font-extrabold text-ink">HEATGUARD <span className="text-heat-500">CLIP</span></h1>
          <p className="text-sm text-slate-500">Prevención del estrés térmico en obras · {SITE.name}</p>
          <ClipLogo active="normal" className="w-32 mx-auto" />
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600">Tu nombre</label>
          <input className="form-input mt-1" placeholder="Ej: Carolina Vidal" value={name} onChange={(e) => setName(e.target.value)} />
        </div>

        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-600">Ingresar como</p>
          {ROLES.map((r) => {
            const IconEl = r.icon;
            const sel = role === r.id;
            return (
              <button type="button" key={r.id} onClick={() => setRole(r.id)}
                className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left cursor-pointer transition-colors ${sel ? 'border-heat-400 bg-heat-50' : 'border-line hover:bg-surface-2'}`}>
                <div className={`p-2 rounded-lg ${sel ? 'bg-heat-500 text-white' : 'bg-surface-2 text-ink-2'}`}><IconEl className="w-4 h-4" /></div>
                <div>
                  <p className="text-sm font-semibold text-ink">{r.label}</p>
                  <p className="text-xs text-slate-500">{r.desc}</p>
                </div>
              </button>
            );
          })}
        </div>

        <button type="submit" className="btn-primary w-full py-2.5">Entrar al panel</button>
        <p className="text-[11px] text-center text-slate-400">Modo demo · los datos de los clips son simulados y no hay autenticación real.</p>
      </form>
    </div>
  );
}
