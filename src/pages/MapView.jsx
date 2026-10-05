import { useApp } from '../context/AppContext';
import SiteMap from '../components/SiteMap';
import { STATUS } from '../lib/risk';

export default function MapView() {
  const { workers, workerStatus } = useApp();
  const counts = {};
  workers.forEach((w) => { const s = workerStatus(w); counts[s] = (counts[s] || 0) + 1; });
  return (
    <div className="page-layout">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Mapa de la obra</h1>
        <p className="text-sm text-slate-500">Posición aproximada de cada clip por zona (simulada). Clic en un punto para ver al trabajador.</p>
      </div>
      <div className="flex gap-2 flex-wrap">
        {Object.keys(STATUS).map((k) => (
          <span key={k} className={`badge ${STATUS[k].badge}`}><span className={`w-2 h-2 rounded-full ${STATUS[k].dot}`} />{STATUS[k].label}: {counts[k] || 0}</span>
        ))}
      </div>
      <div className="card p-2"><SiteMap height={560} /></div>
    </div>
  );
}
