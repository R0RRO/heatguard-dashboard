import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bluetooth, RefreshCw, Smartphone } from 'lucide-react';
import { useApp } from '../context/AppContext';
import StatusBadge from './StatusBadge';
import ClipLogo from './ClipLogo';
import { LoadBar } from './Charts';
import { movDetail } from '../lib/format';
import { hasWbgt } from '../lib/risk';

// Franja fija bajo la barra de navegación con los clips reales: visible en todas las páginas
export default function LiveStrip() {
  const { liveClips, workers, workerStatus } = useApp();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (!liveClips.length) return null;

  return (
    <div className="sticky top-16 z-[1000] bg-emerald-600 text-white shadow-md">
      {liveClips.map((c) => {
        const w = workers.find((x) => x.id === c.workerId);
        if (!w) return null;
        const st = workerStatus(w);
        const age = c.lastAt ? Math.max(0, Math.round((now - c.lastAt) / 1000)) : null;
        const waiting = c.status !== 'connected' || !c.last || age > 8 || w.source !== 'clip';
        const Via = c.via === 'celular' ? Smartphone : Bluetooth;
        return (
          <div key={c.workerId} className="max-w-7xl mx-auto px-4 sm:px-6 py-2 flex items-center gap-x-4 gap-y-1.5 flex-wrap text-sm border-b border-emerald-500/60 last:border-0">
            <span className="inline-flex items-center gap-1.5 font-bold">
              {waiting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Via className="w-4 h-4" />}
              CLIP REAL
              {!waiting && <span className="w-2 h-2 rounded-full bg-white animate-pulse" />}
            </span>
            <Link to={`/workers/${w.id}`} className="font-semibold text-white underline-offset-2 hover:underline">{w.name}</Link>
            {waiting ? (
              <span className="text-emerald-50">{c.status === 'connecting' ? 'Conectando…' : c.last && age <= 8 ? 'Recibiendo lecturas…' : c.via === 'celular' ? 'Sin lecturas recientes del celular…' : 'Se perdió el enlace, reconectando…'}</span>
            ) : (
              <>
                <span className="bg-white rounded-full"><StatusBadge status={st} pulse /></span>
                <ClipLogo active={w.status} className="w-14" />
                <span className="bg-white/95 rounded-full px-2 py-0.5 text-ink"><LoadBar load={w.load} status={st} /></span>
                <span>{w.env.ok ? `${w.env.t.toFixed(1)} °C · ${Math.round(w.env.rh)} % · ${hasWbgt(w) ? `WBGT ${w.wbgt.c.toFixed(1)} °C (${w.wbgt.label.toLowerCase()})` : `sensación térmica (HI) ${w.env.hi.toFixed(1)} °C`}` : 'sensor ambiental sin respuesta'}</span>
                <span>movimiento {movDetail(w.activity * 100)}</span>
                <span className="text-emerald-100 ml-auto">{c.via === 'celular' ? 'vía celular · ' : ''}lectura hace {age} s</span>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
