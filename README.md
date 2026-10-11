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
- **Alertas**: reconocer, ordenar pausa, resolver (salud térmica y dispositivos).
- **Dispositivos**: batería, señal, firmware, inventario.
- **Producto**: prototipo digital con el modelo 3D real del clip (STL en `public/models/`): vista explosionada, interior, accesorios (clip de chaleco / placa de casco), LED y vibración simulados, puntos de interés y ficha técnica. Usa three.js y se carga solo al abrir esa vista.
- **Botón de hidratación**: el clip recuerda beber agua (vibración + LED celeste) pasado el intervalo configurado; el trabajador confirma con una pulsación larga (~1 s, pin D0 a GND). El panel muestra la última hidratación por trabajador, "Hidratación al día", pendientes y alertas si no hay registro. Es un registro autodeclarado: no modifica el puntaje de riesgo. En el visor 3D el botón está en la pared superior (punto 11) y se puede probar en la vista Producto.
- **Umbrales**: sliders para atención / riesgo alto (guardados en localStorage; roles prevencionista y admin).

## Datos simulados
No hay backend. `src/lib/simulation.js` genera telemetría (1 tick = 1 min simulado, cada 1,5 s) y `src/lib/risk.js` calcula el puntaje de riesgo.
Para conectar datos reales, reemplazar el `setInterval` de `src/context/AppContext.jsx` por lecturas de API/WebSocket que entreguen la misma forma de `sim.workers`.
Arriba a la derecha del panel hay controles de simulación (pausa, velocidad, "ola de calor" ±°C).

## Estructura
`src/pages` (vistas) · `src/components` (UI, gráficos SVG propios) · `src/context` (estado) · `src/lib` (riesgo + simulación) · `src/data/seed.js` (obra, zonas, trabajadores).
