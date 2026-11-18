# HeatGuard Clip · Panel de obra y firmware del prototipo

Prototipo del proyecto HeatGuard (ING2030, Grupo 7): un clip que mide el ambiente térmico que rodea al
trabajador y un panel web para que el prevencionista gestione pausas e hidratación.

El repositorio tiene tres partes:

| Carpeta | Qué es |
|---|---|
| `src/` | Panel web (React 19 + Vite + Tailwind 4 + React Router + lucide-react + three.js). |
| `firmware/` | Programa de la XIAO ESP32-C3 del clip (`firmware/heatguard_clip`). Ver `firmware/README.md`. |
| `panel_pruebas/` | Herramientas para probar el hardware: scripts para subir y leer la placa, mini app Bluetooth y programas de diagnóstico. |
| `docs/` | Contrato de datos entre el clip y el panel (`docs/contrato-datos.md`). |

## Correr el panel

```bash
npm install
npm run dev      # panel en http://localhost:5173
npm test         # casos de prueba: Heat Index contra la tabla del NWS, contrato de datos y simulación
npm run lint
```

## Servidor, usuarios y app del trabajador

`server/index.js` (Node 20+, sin dependencias) entrega el panel compilado, maneja el inicio de sesión, corre la simulación de la cuadrilla (la misma para todos los paneles y la app; usa `src/lib/simulation.js`) y reenvía en tiempo real:

- **Roles:** administrador (usuarios, umbrales de pausas, altura y peso, más todo lo del supervisor), supervisor (monitorea, pide o retira pausas, asigna clips a trabajadores en «Usuarios» y maneja los controles de la simulación para demostrar el sistema) y trabajador (su clip). El nombre del usuario trabajador reemplaza al del puesto simulado que tiene asignado.
- **Supervisor** (navegador): ve toda la obra, con la cuadrilla simulada más los clips reales; pide o retira pausas, ajusta las pausas y la altura y peso de cada trabajador. Todo eso se guarda en el servidor (`server/data/`, fuera de git).
- **Trabajador** (Android): la app nativa de `android/` vincula el clip y sigue subiendo lecturas en segundo plano (ver `android/README.md`). También existe la versión web: en Chrome de Android, entrar con el usuario del trabajador y tocar «Vincular clip» (solo funciona con la pantalla abierta). En ambas, el celular reenvía cada lectura al servidor y le pasa al clip las solicitudes de pausa, los umbrales y el factor personal.

Web Bluetooth exige https: por eso el servidor se publica con Tailscale Funnel. La pantalla del celular debe quedar abierta (la app pide mantenerla encendida); si Android pasa Chrome a segundo plano, puede cortar el enlace con el clip.

**Desplegar en rorro-server** (desde tu PC, en la carpeta del repo):

```bash
bash deploy/subir_servidor.sh          # o: bash deploy/subir_servidor.sh usuario@rorro-server
```

Compila, copia a `~/heatguard` del servidor, instala Node si falta (Fedora con dnf, Debian/Ubuntu con NodeSource), crea los usuarios la primera vez con `deploy/credenciales.env` (fuera de git; en el servidor se borra después), deja el servicio `heatguard` de systemd en `127.0.0.1:8787` y lo publica con `tailscale funnel`. Funnel tiene que estar permitido en la consola de Tailscale (si no, el comando entrega el enlace para activarlo).

Usuarios: se gestionan en la página «Usuarios» del panel (administrador), o en el servidor con `node server/usuarios.js lista | clave <usuario> | nuevo <usuario> "<nombre>" <admin|supervisor|trabajador> [w1]` (después `sudo systemctl restart heatguard`). Hay 10 intentos de inicio de sesión cada 10 min por IP; las sesiones duran 12 h (supervisor) o 14 días (trabajador) y sobreviven a un reinicio del servidor.

**Desarrollo local:** en una terminal `HG_SUPERVISOR_PASS=... HG_TRABAJADOR_PASS=... node server/index.js`; en otra `npm run dev` (Vite reenvía `/api` al puerto 8787). Sin servidor, el botón «Modo demo sin servidor» abre el panel como antes (un clip por Bluetooth en ese navegador).

## WBGT estimado (motor Python)

`motor_termico_python/` es el motor de análisis térmico de Jonathan Hinojosa. El servidor lo usa como servicio
local (`integracion/servicio_wbgt.py`): con la temperatura y humedad de cada trabajador, más radiación solar y
viento del pronóstico Open-Meteo para la obra, estima el **WBGT** con el modelo de Ono. Ese WBGT define el factor
de calor de la exposición acumulada (niveles <21, 21–25, 25–28, 28–31 y ≥31 °C → ×1 a ×4) para toda la cuadrilla;
el clip real lo recibe con el comando 11. Sin el servicio o sin meteorología, se vuelve a la sensación térmica
(Heat Index). Es una estimación de modelo, no WBGT medido ni ISO 7243. Detalle en
`motor_termico_python/integracion/CONTRATO_Y_PENDIENTES.md`.

## Alcance y límites

- El clip mide el **ambiente** (temperatura del aire y humedad relativa) y el movimiento del propio clip.
  No mide la fisiología del trabajador.
- El **Heat Index del NWS** es un indicador auxiliar para condiciones de sombra. No incorpora la carga
  radiante del sol o de maquinaria y **no es WBGT/TGBH** (ISO 7243), que requiere temperatura de globo y
  de bulbo húmedo natural: con temperatura y humedad solamente no se puede calcular.
- La **exposición acumulada**, sus factores y umbrales son reglas definidas en este software, sin validar.
- El **índice de movimiento** del acelerómetro es una propuesta sin validar: no mide la tasa metabólica.
  El clip usa la temperatura, la humedad y el movimiento solo para calcular la exposición acumulada.
- El sistema no tiene certificación ISO, no entrega diagnóstico médico, no predice golpes de calor y no
  sustituye la evaluación de un prevencionista.
- No hay comparación con instrumentos de referencia, así que no se declara exactitud.

## Qué incluye el panel

- **Panel**: KPIs, evolución del estado de la cuadrilla, temperatura del aire y Heat Index con las
  categorías del NWS, quién tiene que descansar, quién está cerca del límite, quién está en pausa,
  registro de pausas, alertas abiertas y resumen por zona.
- **Trabajadores** / **detalle**: exposición acumulada, tiempo hasta el límite, pausas, temperatura, humedad,
  Heat Index y su categoría, índice de movimiento, gráficos históricos, dispositivo y acciones. En el detalle
  se editan la altura y el peso de cada trabajador (factor personal; se guardan solo en este navegador).
- **Clip real destacado**: con un clip conectado, una franja verde bajo la barra de navegación muestra su
  estado en todas las páginas, y su trabajador aparece primero y resaltado en las listas.
  Cada trabajador indica si sus datos son simulados o de un clip real.
- **Alertas**: pausas sin comenzar o sin cerrar, y dispositivos (sin conexión, sensor o batería).
- **Dispositivos**: inventario (simulado) y conexión de un **clip real por Bluetooth**.
- **Producto**: modelo 3D de la carcasa v2 (STL en `public/models/`), vista explosionada y ficha técnica.
- **Pausas**: límite de exposición, umbral de cansancio, duración de la pausa y tiempos de alerta (guardados
  en localStorage y enviados al clip real; roles prevencionista y admin), con la explicación del cálculo.

## Indicador térmico: Heat Index del NWS

`src/lib/heatIndex.js` implementa el procedimiento completo del National Weather Service: la fórmula
simple (Steadman) promediada con la temperatura y, si ese valor llega a 80 °F, la regresión de Rothfusz
con sus dos ajustes (humedad bajo 13 % y sobre 85 %). El firmware usa el mismo cálculo
(`firmware/heatguard_clip/heat_index.h`).

Las categorías son las del NWS: Precaución (80 °F / 27 °C), Precaución extrema (90 °F / 32 °C),
Peligro (103 °F / 39 °C) y Peligro extremo (125 °F / 52 °C).

`npm test` compara 24 puntos con la tabla publicada por el NWS (±1 °F). Un hallazgo de esas pruebas: con
humedad sobre 85 % y entre 80 y 87 °F, la tabla impresa no incluye el ajuste del procedimiento (da 87 °F
para 80 °F y 100 %; el procedimiento completo da 89 °F).

## Exposición acumulada y pausas de hidratación y descanso

El clip pide pausas cuando el trabajador acumula cierto tiempo expuesto al calor y moviéndose
(`src/lib/risk.js`, mismo cálculo en el firmware). Cada minuto suma exposición según la categoría del Heat
Index (×1 a ×4), el índice de movimiento (×0,75 a ×1,25) y un factor personal según el IMC del trabajador
(×1 a ×1,2); al 100 % toca descanso. Estados y LED del clip:
óptimo (verde parpadeante), cansancio (amarillo), toca descanso (rojo + 5 vibraciones cada 40 s),
en pausa (azul fijo) y pausa cumplida (azul parpadeante + vibración). Límite, umbral de cansancio y
duración de la pausa se configuran en la página «Pausas». Son reglas del prototipo, sin validar.

## Datos simulados y datos reales

Sin backend. `src/lib/simulation.js` genera la telemetría (1 tick = 1 minuto simulado, cada 1,5 s reales);
arriba a la derecha del panel hay controles de simulación (pausa, velocidad, «ola de calor» ±°C).

Para usar un clip real: en **Dispositivos → Clip real por Bluetooth**, presiona *Conectar clip* y elige
a qué trabajador asignarlo. Requiere Chrome, Chromium o Edge (Web Bluetooth) y abrir el panel desde
`localhost` o https. Las lecturas del clip reemplazan a las simuladas de ese trabajador; el resto de la
cuadrilla sigue simulado. Si el enlace se cae, el panel reintenta solo y, mientras tanto, muestra al
trabajador «Sin señal» en vez de inventar valores. El clip calcula su exposición acumulada y su estado; el panel le envía
la configuración de «Pausas» y los pedidos de pausa del supervisor.

El mensaje que intercambian está en `docs/contrato-datos.md` (`src/lib/telemetry.js` en el panel).
Para conectar otro transporte (API o WebSocket), entregar ese mismo mensaje a `step()` como hace
`src/context/AppContext.jsx` con `src/lib/clipLink.js`.

## Botón del clip

Nadie entra ni sale de una pausa sin el botón del clip (pin D0 a GND), y hay que mantenerlo 2 s para que no
se active por accidente: comienza la pausa (pedida por el clip o el supervisor, o voluntaria) y, en pausa,
la termina. El supervisor solo puede *pedir* una pausa o retirar su pedido. Si una pausa pedida no
comienza, o una cumplida no se cierra, en el tiempo configurado, el panel abre una alerta.

En la simulación, los trabajadores responden con el botón solo cuando el clip lo pide (se puede apagar en
«Pausas»); en el detalle de cada trabajador simulado hay un botón para simular la pulsación.

## Estructura del panel

`src/pages` (vistas) · `src/components` (UI, gráficos SVG propios) · `src/context` (estado y enlace con
el clip) · `src/lib` (Heat Index, riesgo, simulación, contrato de datos, Bluetooth) ·
`src/data/seed.js` (obra, zonas y trabajadores ficticios).
