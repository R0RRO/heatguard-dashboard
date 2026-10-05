export default function KpiCard({ icon, label, value, unit, hint, tone = 'navy' }) {
  const IconEl = icon;
  const tones = {
    navy: 'bg-surface-2 text-ink-2',
    heat: 'bg-heat-100 text-heat-600',
    red: 'bg-red-50 text-red-600',
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
  };
  return (
    <div className="card p-4 flex items-start gap-3">
      <div className={`rounded-lg p-2.5 ${tones[tone]}`}><IconEl className="w-5 h-5" /></div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <p className="text-2xl font-bold text-ink leading-tight">
          {value}{unit && <span className="text-sm font-semibold text-slate-400 ml-1">{unit}</span>}
        </p>
        {hint && <p className="text-xs text-slate-400 mt-0.5 truncate">{hint}</p>}
      </div>
    </div>
  );
}
