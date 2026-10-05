import { STATUS } from '../lib/risk';

export default function StatusBadge({ status, pulse = false }) {
  const s = STATUS[status];
  return (
    <span className={`badge ${s.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${pulse && status === 'alerta' ? 'pulse-crit' : ''}`} />
      {s.label}
    </span>
  );
}
