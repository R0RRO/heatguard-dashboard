import { useEffect, useRef, useState } from 'react';

// Mantiene el orden de una lista fijo y lo recalcula cada `ms` (por defecto 10 s), para que las filas no
// salten mientras los valores se actualizan. Si cambian los filtros u orden elegidos (`key`), se reordena al tiro.
// Los elementos nuevos se agregan al final hasta el próximo reordenamiento; los que salen, desaparecen.
export function useStableOrder(list, key = '', ms = 10000) {
  const ids = list.map((x) => x.id);
  const latest = useRef(ids);
  useEffect(() => { latest.current = ids; });
  const [state, setState] = useState({ key, order: ids });
  if (state.key !== key) setState({ key, order: ids });
  useEffect(() => {
    const t = setInterval(() => setState((s) => ({ ...s, order: latest.current })), ms);
    return () => clearInterval(t);
  }, [ms]);

  const order = state.key === key ? state.order : ids;
  const byId = new Map(list.map((x) => [x.id, x]));
  const seen = new Set();
  const out = [];
  for (const id of order) if (byId.has(id) && !seen.has(id)) { out.push(byId.get(id)); seen.add(id); }
  for (const x of list) if (!seen.has(x.id)) out.push(x);
  return out;
}
