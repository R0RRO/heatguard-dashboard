import { STATUS } from '../lib/risk';

export default function StatusBadge({ status, pulse = false }) {
  const s = STATUS[status] || STATUS.normal;
  const urgent = status === 'descanso' || status === 'finPausa';
  return (
    <span className={`badge ${s.badge}`} title={`LED del clip: ${s.led}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${pulse && urgent ? 'pulse-crit' : ''}`} />
      {s.label}
    </span>
  );
}
