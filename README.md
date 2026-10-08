# HeatGuard Clip · Panel de obra (boceto)

Dashboard web para monitorear en tiempo real los clips wearable HeatGuard de los trabajadores de una obra y prevenir estrés térmico.
Mismo stack que IIC3113-Frontend: React 19 + Vite + Tailwind 4 + React Router + Leaflet + lucide-react.

## Correr
```bash
npm install
npm run dev
```

## Qué incluye
- **Panel**: KPIs, evolución del estado de la cuadrilla, clima, quién requiere pausa, alertas abiertas, resumen por zona.
- **Trabajadores** / **detalle**: T° y humedad ambiente, exposición, actividad, riesgo, gráficos históricos, dispositivo, acciones (pausa / hidratación).
- **Mapa**: zonas y clips sobre Leaflet con color de semáforo (verde / azul / rojo).
- **Alertas**: reconocer, ordenar pausa, resolver (salud térmica, seguridad y dispositivos).
- **Acelerómetro (simulado)**: actividad (% y g RMS), pasos y recorrido estimado (últimos 30 min), detección de caídas y de falta de movimiento prolongada (umbral configurable).
- **Dispositivos**: batería, señal, firmware, inventario.
- **Producto**: prototipo digital con el modelo 3D real del clip (STL en `public/models/`): vista explosionada, interior, accesorios (clip de chaleco / placa de casco), LED y vibración simulados, puntos de interés y ficha técnica. Usa three.js y se carga solo al abrir esa vista.
- **Umbrales**: sliders para atención / riesgo alto (guardados en localStorage; roles prevencionista y admin).

## Datos simulados
No hay backend. `src/lib/simulation.js` genera telemetría (1 tick = 1 min simulado, cada 1,5 s) y `src/lib/risk.js` calcula el puntaje de riesgo.
Para conectar datos reales, reemplazar el `setInterval` de `src/context/AppContext.jsx` por lecturas de API/WebSocket que entreguen la misma forma de `sim.workers`.
Arriba a la derecha del panel hay controles de simulación (pausa, velocidad, "ola de calor" ±°C).

## Estructura
`src/pages` (vistas) · `src/components` (UI, gráficos SVG propios, mapa) · `src/context` (estado) · `src/lib` (riesgo + simulación) · `src/data/seed.js` (obra, zonas, trabajadores).

## Despliegue (Cloudflare)
Sitio estático (Vite). Se despliega con `wrangler.jsonc`, que ya incluye el fallback para las rutas de React Router.

- **Desde GitHub (recomendado):** Cloudflare → Workers & Pages → Create → Import a repository. Build command: `npm run build` · Deploy command: `npx wrangler deploy`. Cada `git push` a `main` redespliega.
- **Directo desde tu computador:** `npm run build && npx wrangler deploy` (la primera vez pide `npx wrangler login`).
