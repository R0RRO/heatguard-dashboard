import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import { useApp } from '../context/AppContext';

export default function Toasts() {
  const { toasts, dismissToast } = useApp();
  return (
    <div className="fixed bottom-4 right-4 z-[2000] space-y-2 w-[min(92vw,340px)]">
      {toasts.map((t) => {
        const crit = t.level === 'alerta';
        return (
          <div key={t.id} className={`toast-in flex items-start gap-2 rounded-xl px-3 py-2.5 shadow-lg border text-sm ${crit ? 'bg-red-600 text-white border-red-500' : 'bg-surface text-ink border-line'}`}>
            {crit ? <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> : <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-green-600" />}
            <span className="flex-1">{t.text}</span>
            <button onClick={() => dismissToast(t.id)} className="opacity-70 hover:opacity-100 cursor-pointer"><X className="w-4 h-4" /></button>
          </div>
        );
      })}
    </div>
  );
}
