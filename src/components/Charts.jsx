import { useState } from 'react';
import { fmtClock } from '../lib/format';

const W = 600;
const H = 200;
const PAD = { l: 34, r: 10, t: 10, b: 22 };

function scale(domain, range) {
  const [d0, d1] = domain;
  return (v) => range[0] + ((v - d0) / (d1 - d0 || 1)) * (range[1] - range[0]);
}

// Gráfico de líneas (varias series) con líneas de referencia y tooltip
export function LineChart({ data, lines, yDomain, refLines = [] }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return null;
  const [y0, y1] = yDomain || [
    Math.min(...lines.flatMap((l) => data.map((d) => d[l.key]))),
    Math.max(...lines.flatMap((l) => data.map((d) => d[l.key]))),
  ];
  const x = scale([0, data.length - 1], [PAD.l, W - PAD.r]);
  const y = scale([y0, y1], [H - PAD.b, PAD.t]);
  const ticks = Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4);
  const xTicks = [0, Math.floor((data.length - 1) / 2), data.length - 1];

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const idx = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (data.length - 1));
    setHover(Math.min(data.length - 1, Math.max(0, idx)));
  };

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-slate-200" strokeWidth="1" />
            <text x={PAD.l - 6} y={y(t) + 3} textAnchor="end" fontSize="10" className="fill-slate-400">{Math.round(t)}</text>
          </g>
        ))}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor="middle" fontSize="10" className="fill-slate-400">{fmtClock(data[i].clock)}</text>
        ))}
        {refLines.map((r) => (
          <g key={r.label}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(r.value)} y2={y(r.value)} stroke={r.color} strokeDasharray="4 4" strokeWidth="1.2" />
            <text x={W - PAD.r - 2} y={y(r.value) - 3} textAnchor="end" fontSize="9" fill={r.color}>{r.label}</text>
          </g>
        ))}
        {lines.map((l) => (
          <polyline
            key={l.key}
            fill="none"
            stroke={l.color}
            strokeWidth="2"
            strokeLinejoin="round"
            points={data.map((d, i) => `${x(i)},${y(d[l.key])}`).join(' ')}
          />
        ))}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} className="stroke-slate-400" strokeDasharray="3 3" />
            {lines.map((l) => <circle key={l.key} cx={x(hover)} cy={y(data[hover][l.key])} r="3.5" fill={l.color} className="stroke-surface" strokeWidth="1.5" />)}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div
          className="absolute top-1 bg-navy-900 text-white border border-white/10 text-xs rounded-lg px-2.5 py-1.5 pointer-events-none shadow-lg"
          style={{ left: `${(x(hover) / W) * 100}%`, transform: `translateX(${hover > data.length / 2 ? '-105%' : '5%'})` }}
        >
          <p className="font-semibold mb-0.5">{fmtClock(data[hover].clock)}</p>
          {lines.map((l) => (
            <p key={l.key} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ background: l.color }} />
              {l.label}: <b>{Math.round(data[hover][l.key] * 10) / 10}{l.unit || ''}</b>
            </p>
          ))}
        </div>
      )}
      <div className="flex gap-4 justify-center mt-1 flex-wrap">
        {lines.map((l) => (
          <span key={l.key} className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className="w-3 h-0.5 rounded" style={{ background: l.color, height: 3 }} />{l.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// Área apilada por estado (normal / atención / alerta)
export function StackedArea({ data, series }) {
  if (!data.length) return null;
  const total = data.reduce((m, d) => Math.max(m, series.reduce((a, s) => a + d[s.key], 0)), 1);
  const x = scale([0, data.length - 1], [PAD.l, W - PAD.r]);
  const y = scale([0, total], [H - PAD.b, PAD.t]);
  const cum = data.map(() => 0);
  const paths = series.map((s) => {
    const lower = cum.slice();
    data.forEach((d, i) => { cum[i] += d[s.key]; });
    const upper = cum.slice();
    const top = data.map((_, i) => `${x(i)},${y(upper[i])}`).join(' L');
    const bottom = data.map((_, i) => `${x(data.length - 1 - i)},${y(lower[data.length - 1 - i])}`).join(' L');
    return { ...s, d: `M${top} L${bottom} Z` };
  });
  const xTicks = [0, Math.floor((data.length - 1) / 2), data.length - 1];
  const yTicks = [0, Math.round(total / 2), total];
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-slate-200" />
            <text x={PAD.l - 6} y={y(t) + 3} textAnchor="end" fontSize="10" className="fill-slate-400">{t}</text>
          </g>
        ))}
        {paths.map((p) => <path key={p.key} d={p.d} fill={p.color} opacity="0.9" />)}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor="middle" fontSize="10" className="fill-slate-400">{fmtClock(data[i].clock)}</text>
        ))}
      </svg>
      <div className="flex gap-4 justify-center mt-1">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} />{s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function Donut({ segments, center, size = 150 }) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const r = 52;
  const c = 2 * Math.PI * r;
  const arcs = segments.reduce((acc, sg) => {
    const len = (sg.value / total) * c;
    const offset = acc.length ? acc[acc.length - 1].offset + acc[acc.length - 1].len : 0;
    return [...acc, { ...sg, len, offset }];
  }, []);
  return (
    <svg viewBox="0 0 140 140" width={size} height={size} className="mx-auto">
      <circle cx="70" cy="70" r={r} fill="none" className="stroke-slate-200" strokeWidth="16" />
      {arcs.map((s) => (
        <circle
          key={s.label}
          cx="70" cy="70" r={r} fill="none" stroke={s.color} strokeWidth="16"
          strokeDasharray={`${s.len} ${c - s.len}`} strokeDashoffset={-s.offset}
          transform="rotate(-90 70 70)"
        />
      ))}
      {center && (
        <>
          <text x="70" y="70" textAnchor="middle" fontSize="26" fontWeight="700" className="fill-ink">{center.value}</text>
          <text x="70" y="86" textAnchor="middle" fontSize="9" className="fill-slate-500">{center.label}</text>
        </>
      )}
    </svg>
  );
}

export function Sparkline({ values, color = '#f97316', width = 90, height = 26 }) {
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const x = scale([0, values.length - 1], [1, width - 1]);
  const y = scale([min, max === min ? min + 1 : max], [height - 2, 2]);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" points={values.map((v, i) => `${x(i)},${y(v)}`).join(' ')} />
    </svg>
  );
}

export function RiskBar({ score, status }) {
  const colors = { alerta: 'bg-red-500', atencion: 'bg-blue-500', normal: 'bg-green-500' };
  return (
    <div className="flex items-center gap-2 min-w-[110px]">
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${colors[status]}`} style={{ width: `${Math.min(100, score)}%` }} />
      </div>
      <span className="text-xs font-semibold text-slate-600 w-7 text-right">{Math.round(score)}</span>
    </div>
  );
}

export function BatteryPill({ level }) {
  const tone = level < 15 ? 'text-red-600' : level < 35 ? 'text-amber-600' : 'text-slate-600';
  const fill = level < 15 ? 'bg-red-500' : level < 35 ? 'bg-amber-500' : 'bg-green-500';
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${tone}`}>
      <span className="relative w-6 h-3 border border-slate-400 rounded-[3px]">
        <span className={`absolute inset-0.5 rounded-[1px] ${fill}`} style={{ width: `${Math.max(4, level)}%`, right: 'auto' }} />
      </span>
      {Math.round(level)}%
    </span>
  );
}
