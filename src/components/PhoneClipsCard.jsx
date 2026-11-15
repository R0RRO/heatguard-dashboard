import { Smartphone, Vibrate, Server } from 'lucide-react';
import { useApp } from '../context/AppContext';

const LINK_TEXT = { connecting: 'conectando', connected: 'enlazado', reconnecting: 'reconectando' };

// Clips reales enlazados desde la app del trabajador (celular Android) y reenviados por el servidor
export default function PhoneClipsCard() {
  const { token, server, liveClips, workers, identifyWorkerClip } = useApp();
  if (!token) {
    return <div className="card p-4 text-sm text-slate-500 flex gap-2 items-start"><Server className="w-4 h-4 mt-0.5 shrink-0" />Modo demo sin servidor.</div>;
  }
  const phones = liveClips.filter((c) => c.via === 'celular');
  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="rounded-lg p-2.5 bg-surface-2 text-ink-2"><Smartphone className="w-5 h-5" /></div>
        <div className="flex-1 min-w-[200px]">
          <p className="font-bold text-ink">Clips enlazados desde celulares</p>
          <p className="text-xs text-slate-500">
            Servidor: {server.status === 'connected' ? 'en línea' : server.status === 'reconnecting' ? 'reconectando…' : 'desconectado'}
          </p>
        </div>
      </div>
      {phones.length === 0
        ? <p className="text-sm text-slate-500">Sin clips enlazados.</p>
        : (
          <ul className="divide-y divide-line">
            {phones.map((c) => {
              const w = workers.find((x) => x.id === c.workerId);
              return (
                <li key={c.workerId} className="py-2 flex items-center gap-3 flex-wrap text-sm">
                  <span className="font-semibold text-ink">{w?.name || c.workerId}</span>
                  <span className="text-slate-500">{c.deviceName || 'clip'} · {LINK_TEXT[c.status] || c.status}{c.by ? ` · usuario ${c.by}` : ''}</span>
                  <button className="btn-secondary btn-sm ml-auto" onClick={() => identifyWorkerClip(c.workerId)} title="El clip parpadea y vibra"><Vibrate className="w-3.5 h-3.5" />Ubicar</button>
                </li>
              );
            })}
          </ul>
        )}
    </div>
  );
}
