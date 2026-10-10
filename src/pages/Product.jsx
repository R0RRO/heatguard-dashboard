import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RotateCcw, Layers, Eye, Tag, Cable, BellRing, MousePointerClick, Vibrate, BatteryLow, ArrowRight, Info } from 'lucide-react';
import ClipViewer from '../components/ClipViewer';
import { NETS } from '../lib/wiring';
import { HOTSPOTS, LED_STATES, SIGNALS, SPECS, COMPONENTS, MOUNTS } from '../data/product';

function Toggle({ on, onClick, icon, label }) {
  const IconEl = icon;
  return (
    <button onClick={onClick} className={on ? 'btn-filter-active inline-flex items-center gap-1.5' : 'btn-filter inline-flex items-center gap-1.5'}>
      <IconEl className="w-3.5 h-3.5" />{label}
    </button>
  );
}

export default function Product() {
  const [ledState, setLedState] = useState('normal');
  const [batteryLow, setBatteryLow] = useState(false);
  const [vibrate, setVibrate] = useState(false);
  const [explode, setExplode] = useState(0);
  const [interior, setInterior] = useState(false);
  const [accessory, setAccessory] = useState('none');
  const [autoRotate, setAutoRotate] = useState(true);
  const [wires, setWires] = useState(false);
  const [reminder, setReminder] = useState(false);
  const [pressKey, setPressKey] = useState(0);
  const [drinks, setDrinks] = useState(0);
  const [labels, setLabels] = useState(true);
  const [selected, setSelected] = useState(null);
  const [resetKey, setResetKey] = useState(0);

  const hotspot = HOTSPOTS.find((h) => h.id === selected);
  const select = (id) => {
    setSelected(id);
    const h = HOTSPOTS.find((x) => x.id === id);
    if (h?.interior) setInterior(true);
  };
  // Botón de hidratación (simulado): registra la toma, apaga el recordatorio y el clip confirma
  const pressButton = () => {
    setPressKey((n) => n + 1);
    setDrinks((n) => n + 1);
    setReminder(false);
  };
  const setAlert = (k) => {
    setLedState(k);
    setVibrate(k === 'alerta');
  };

  return (
    <div className="page-layout">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="text-xs font-bold tracking-widest text-heat-600 uppercase">Prototipo digital · v2</p>
          <h1 className="text-3xl font-extrabold text-ink">HeatGuard <span className="text-heat-500">Clip</span></h1>
          <p className="text-sm text-slate-500 max-w-2xl mt-1">
            Dispositivo que se fija al casco o al chaleco y mide la temperatura, la humedad y el movimiento alrededor del trabajador. Avisa con luz y vibración, registra la hidratación con un botón y envía los datos por Bluetooth a este panel.
          </p>
        </div>
        <span className="badge bg-surface-2 text-ink-2 border-line-2">Modelo 3D real · carcasa 80 × 40 × 17 mm</span>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Visor */}
        <div className="card lg:col-span-2 overflow-hidden flex flex-col">
          <div className="flex items-center gap-2 flex-wrap p-3 border-b border-line">
            {Object.entries(MOUNTS).map(([k, m]) => (
              <button key={k} onClick={() => setAccessory(k)} className={accessory === k ? 'btn-filter-active' : 'btn-filter'}>{m.label}</button>
            ))}
            <button onClick={() => setResetKey((n) => n + 1)} className="btn-secondary btn-sm ml-auto"><RotateCcw className="w-3.5 h-3.5" />Restablecer vista</button>
          </div>

          <div className="relative h-[460px] sm:h-[540px] bg-gradient-to-b from-surface-2 to-surface">
            <ClipViewer
              ledState={ledState} batteryLow={batteryLow} vibrate={vibrate} explode={explode} interior={interior} wires={wires} reminder={reminder} pressKey={pressKey}
              accessory={accessory} autoRotate={autoRotate} showLabels={labels} selected={selected}
              onSelect={select} resetKey={resetKey}
            />
            <p className="absolute left-3 bottom-2 text-[11px] text-slate-400 pointer-events-none">Arrastra para girar · rueda para acercar</p>
          </div>

          <div className="p-3 border-t border-line space-y-3">
            <div className="flex items-center gap-3">
              <Layers className="w-4 h-4 text-ink-2 shrink-0" />
              <label htmlFor="explode" className="text-sm font-medium text-ink w-24 shrink-0">Explosionar</label>
              <input id="explode" type="range" min="0" max="1" step="0.01" value={explode} onChange={(e) => setExplode(+e.target.value)} className="flex-1 accent-orange-500" />
            </div>
            {wires && (
              <div className="rounded-lg border border-line bg-surface-2 p-2.5">
                <p className="text-xs font-semibold text-ink mb-1.5">Conexiones (según esquema eléctrico)</p>
                <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1">
                  {Object.values(NETS).map((n) => (
                    <div key={n.label} className="flex items-center gap-2 text-xs text-ink-2">
                      <span className="w-4 h-1.5 rounded-full shrink-0 ring-1 ring-black/10" style={{ background: n.color }} />{n.label}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="flex gap-2 flex-wrap">
              <Toggle on={interior} onClick={() => setInterior(!interior)} icon={Eye} label="Ver interior" />
              <Toggle on={wires} onClick={() => { if (!wires) setInterior(true); setWires(!wires); }} icon={Cable} label="Cables" />
              <Toggle on={labels} onClick={() => setLabels(!labels)} icon={Tag} label="Puntos de interés" />
              <Toggle on={autoRotate} onClick={() => setAutoRotate(!autoRotate)} icon={RotateCcw} label="Rotación automática" />
            </div>
            <p className="text-xs text-slate-500">{MOUNTS[accessory].text}</p>
          </div>
        </div>

        {/* Panel lateral */}
        <div className="space-y-6">
          <div className="card p-4 space-y-3">
            <h2 className="section-heading">Simular el clip</h2>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(LED_STATES).map(([k, s]) => (
                <button key={k} onClick={() => setAlert(k)}
                  className={`rounded-lg border px-2 py-2 text-xs font-semibold cursor-pointer transition-colors ${ledState === k ? 'text-white border-transparent' : 'bg-surface text-ink border-line-2 hover:bg-surface-2'}`}
                  style={ledState === k ? { background: s.color } : undefined}>
                  <span className="block w-2.5 h-2.5 rounded-full mx-auto mb-1" style={{ background: ledState === k ? '#fff' : s.color }} />
                  {s.label}
                </button>
              ))}
            </div>
            <p className="text-sm text-slate-600">{LED_STATES[ledState].text}</p>
            <div className="flex gap-2 flex-wrap">
              <Toggle on={vibrate} onClick={() => setVibrate(!vibrate)} icon={Vibrate} label="Vibración" />
              <Toggle on={batteryLow} onClick={() => setBatteryLow(!batteryLow)} icon={BatteryLow} label="Batería baja" />
            </div>
          </div>

          <div className="card p-4 space-y-3">
            <h2 className="section-heading"><MousePointerClick className="w-4 h-4 text-ink-2" />Botón de hidratación</h2>
            <p className="text-sm text-slate-600">Cuando pasa el intervalo configurado sin registro, el clip recuerda con {SIGNALS.recordatorio.text.toLowerCase()} El trabajador toma agua y mantiene presionado el botón ~1 s.</p>
            <div className="flex gap-2 flex-wrap">
              <Toggle on={reminder} onClick={() => setReminder(!reminder)} icon={BellRing} label="Activar recordatorio" />
              <button onClick={pressButton} className="btn-primary btn-sm inline-flex items-center gap-1.5"><MousePointerClick className="w-3.5 h-3.5" />Presionar botón</button>
            </div>
            <p className="text-xs text-slate-500" aria-live="polite">
              {drinks === 0 ? 'El botón está en la pared superior del clip (punto 11).' : `${SIGNALS.registro.text} Registros en esta sesión: ${drinks}.`}
            </p>
            <p className="text-xs text-slate-500">Es un registro autodeclarado: no mide hidratación ni reinicia el riesgo térmico ni las alertas.</p>
          </div>

          <div className="card p-4 space-y-2">
            <h2 className="section-heading">Puntos de interés</h2>
            <div className="space-y-1 max-h-[260px] overflow-y-auto pr-1">
              {HOTSPOTS.map((h) => (
                <button key={h.id} onClick={() => select(h.id)}
                  className={`w-full flex items-center gap-2.5 text-left px-2 py-1.5 rounded-lg cursor-pointer transition-colors ${selected === h.id ? 'bg-heat-50' : 'hover:bg-surface-2'}`}>
                  <span className={`w-5 h-5 rounded-full text-[11px] font-bold flex items-center justify-center shrink-0 ${selected === h.id ? 'bg-heat-500 text-white' : 'bg-navy-900 text-white'}`}>{h.n}</span>
                  <span className="text-sm text-ink flex-1">{h.title}</span>
                  {h.interior && <span className="text-[10px] text-slate-400">interior</span>}
                </button>
              ))}
            </div>
            {hotspot ? (
              <div className="rounded-lg bg-surface-2 border border-line p-3 text-sm">
                <p className="font-semibold text-ink">{hotspot.title}</p>
                <p className="text-slate-600 mt-0.5">{hotspot.desc}</p>
              </div>
            ) : (
              <p className="text-xs text-slate-500 flex items-center gap-1.5"><Info className="w-3.5 h-3.5" />Elige un punto para ver su función.</p>
            )}
          </div>
        </div>
      </div>

      <div>
        <h2 className="section-heading mb-3">Ficha técnica</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {SPECS.map((s) => (
            <div key={s.title} className="card p-4">
              <h3 className="text-xs font-bold uppercase tracking-wide text-heat-600 mb-2">{s.title}</h3>
              <dl className="space-y-2">
                {s.rows.map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-slate-500">{k}</dt>
                    <dd className="text-sm font-medium text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card overflow-x-auto">
          <h2 className="section-heading p-4 pb-2">Componentes principales</h2>
          <table className="w-full">
            <thead className="border-b border-line bg-surface-2/50"><tr><th className="th">Componente</th><th className="th">Función</th><th className="th">Conexión</th></tr></thead>
            <tbody>
              {COMPONENTS.map(([a, b, c]) => (
                <tr key={a} className="border-b border-slate-50">
                  <td className="td font-medium text-ink">{a}</td><td className="td text-slate-600 whitespace-normal">{b}</td><td className="td font-mono text-xs text-slate-600">{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="space-y-6">
          <div className="card p-4 space-y-2">
            <h2 className="section-heading">Qué ve la plataforma</h2>
            <p className="text-sm text-slate-600">Cada clip envía por Bluetooth, de forma periódica: temperatura y humedad ambiente, nivel de actividad y pasos, tiempo de exposición, estado de riesgo y nivel de batería. Con eso el prevencionista ve en este panel quién necesita una pausa.</p>
            <Link to="/workers" className="back-link">Ver trabajadores en vivo <ArrowRight className="w-3 h-3" /></Link>
          </div>
          <div className="card p-4 space-y-2 border-heat-200">
            <h2 className="section-heading">Alcance y límites</h2>
            <ul className="text-sm text-slate-600 space-y-1.5 list-disc pl-5">
              <li>Mide el <b>ambiente</b> que rodea al trabajador; no mide su fisiología (pulso o temperatura de piel).</li>
              <li>No reemplaza la medición normada de carga calórica (TGBH, DS 594). Los umbrales de alerta son configurables.</li>
              <li>Datos de este panel: simulados. El modelo 3D es el diseño real de la carcasa.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
