import { useState } from 'react';
import { BellOff } from 'lucide-react';
import { useApp } from '../context/AppContext';
import AlertItem from '../components/AlertItem';

const TABS = [['activa', 'Activas'], ['reconocida', 'Reconocidas'], ['resuelta', 'Resueltas'], ['all', 'Todas']];
const KINDS = [['all', 'Todo'], ['salud', 'Salud'], ['seguridad', 'Seguridad'], ['dispositivo', 'Dispositivo']];

export default function Alerts() {
  const { alerts } = useApp();
  const [tab, setTab] = useState('activa');
  const [kind, setKind] = useState('all');
  const list = alerts.filter((a) => (tab === 'all' || a.status === tab) && (kind === 'all' || a.kind === kind));
  const counts = (s) => alerts.filter((a) => s === 'all' || a.status === s).length;

  return (
    <div className="page-layout">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Alertas</h1>
        <p className="text-sm text-slate-500">Reconoce, ordena pausas y cierra alertas de salud térmica y de dispositivos.</p>
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className={tab === k ? 'btn-filter-active' : 'btn-filter'}>{label} ({counts(k)})</button>
        ))}
        <span className="w-px h-5 bg-line mx-1" />
        {KINDS.map(([k, label]) => (
          <button key={k} onClick={() => setKind(k)} className={kind === k ? 'btn-filter-active' : 'btn-filter'}>{label}</button>
        ))}
      </div>
      {list.length === 0 ? (
        <div className="card p-12 text-center text-slate-500"><BellOff className="w-8 h-8 mx-auto mb-2 text-slate-300" />No hay alertas en esta vista.</div>
      ) : (
        <div className="space-y-2">{list.map((a) => <AlertItem key={a.id} alert={a} />)}</div>
      )}
    </div>
  );
}
