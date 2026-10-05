// Ilustración simplificada del clip con sus 3 LEDs (verde / azul / rojo)
export default function ClipLogo({ active = 'normal', className = 'w-28' }) {
  const on = (k) => (active === k ? 1 : 0.18);
  return (
    <svg viewBox="0 0 120 44" className={className}>
      <rect x="2" y="6" width="116" height="32" rx="16" fill="#1e293b" />
      <circle cx="22" cy="22" r="12" fill="#94a3b8" />
      <circle cx="22" cy="22" r="9" fill="#cbd5e1" />
      <circle cx="58" cy="22" r="3.5" fill="#22c55e" opacity={on('normal')} />
      <circle cx="74" cy="22" r="3.5" fill="#3b82f6" opacity={on('atencion')} />
      <circle cx="90" cy="22" r="3.5" fill="#ef4444" opacity={on('alerta')} />
    </svg>
  );
}
