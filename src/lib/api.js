// Cliente del servidor HeatGuard (server/index.js): sesión, estado compartido y tiempo real
const KEY = 'hg_session';

export function loadSession() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; }
}
export function saveSession(s) {
  try { if (s) localStorage.setItem(KEY, JSON.stringify(s)); else localStorage.removeItem(KEY); } catch { /* sin storage */ }
}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function request(path, { token, method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: { ...(body ? { 'content-type': 'application/json' } : {}), ...(token ? { authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('No se pudo contactar al servidor. Revisa la conexión.', 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error || `Error ${res.status}`, res.status);
  return data;
}

export const apiLogin = (usuario, clave) => request('/api/login', { method: 'POST', body: { usuario, clave } });

// Flujo de eventos del servidor (EventSource reconecta solo). handlers: { evento: fn(datos) }
export function openStream(token, handlers, { workerId, onOpen, onError } = {}) {
  const q = new URLSearchParams({ token, ...(workerId ? { workerId } : {}) });
  const es = new EventSource(`/api/stream?${q}`);
  for (const [ev, fn] of Object.entries(handlers)) es.addEventListener(ev, (e) => { try { fn(JSON.parse(e.data)); } catch { /* ignorar */ } });
  es.onopen = () => onOpen?.();
  es.onerror = () => onError?.(es.readyState);
  return es;
}
