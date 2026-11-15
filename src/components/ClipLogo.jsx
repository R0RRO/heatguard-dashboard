import { STATUS } from '../lib/risk';

// Ilustración simplificada del clip con su LED de estado (mismo color que el LED real)
export default function ClipLogo({ active = 'normal', className = 'w-28' }) {
  const s = STATUS[active] || STATUS.normal;
  const blink = active === 'normal' || active === 'finPausa';
  return (
    <svg viewBox="0 0 120 44" className={className} aria-label={`LED del clip: ${s.led}`}>
      <rect x="2" y="6" width="116" height="32" rx="16" fill="#1e293b" />
      <circle cx="22" cy="22" r="12" fill="#94a3b8" />
      <circle cx="22" cy="22" r="9" fill="#cbd5e1" />
      <circle cx="74" cy="22" r="9" fill={s.hex} opacity="0.25" />
      <circle cx="74" cy="22" r="5" fill={s.hex}>
        {blink && <animate attributeName="opacity" values="1;0.2;1" dur={active === 'finPausa' ? '0.8s' : '2.4s'} repeatCount="indefinite" />}
      </circle>
      <circle cx="98" cy="22" r="3" fill="#475569" />
    </svg>
  );
}
