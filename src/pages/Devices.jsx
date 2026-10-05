import { Link } from 'react-router-dom';
import { BatteryLow, Wifi, WifiOff, Package } from 'lucide-react';
import { useApp } from '../context/AppContext';
import KpiCard from '../components/KpiCard';
import { BatteryPill } from '../components/Charts';

export default function Devices() {
  const { workers, sim } = useApp();
  const online = workers.filter((w) => w.online).length;
  const low = workers.filter((w) => w.battery < 20).length;
  const sorted = [...workers].sort((a, b) => a.battery - b.battery);

  return (
    <div className="page-layout">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Dispositivos</h1>
        <p className="text-sm text-slate-500">Inventario y salud de los clips HeatGuard.</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard icon={Wifi} label="En línea" value={online} tone="green" hint={`de ${workers.length} asignados`} />
        <KpiCard icon={WifiOff} label="Sin señal" value={workers.length - online} tone="red" />
        <KpiCard icon={BatteryLow} label="Batería < 20%" value={low} tone="heat" />
        <KpiCard icon={Package} label="En bodega" value={sim.spare.length} tone="navy" hint="listos para asignar" />
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line bg-surface-2/50">
            <tr><th className="th">Clip</th><th className="th">Asignado a</th><th className="th">Montaje</th><th className="th">Batería</th><th className="th">Señal BLE</th><th className="th">Firmware</th><th className="th">Estado</th></tr>
          </thead>
          <tbody>
            {sorted.map((w) => (
              <tr key={w.id} className="border-b border-slate-50">
                <td className="td font-mono font-semibold">{w.deviceId}</td>
                <td className="td"><Link to={`/workers/${w.id}`} className="text-ink-2 hover:text-heat-600 no-underline font-medium">{w.name}</Link></td>
                <td className="td capitalize text-slate-600">{w.mount}</td>
                <td className="td"><BatteryPill level={w.battery} /></td>
                <td className="td text-slate-600">{Math.round(w.signal)} dBm</td>
                <td className="td text-slate-600">1.4.2</td>
                <td className="td">{w.online
                  ? <span className="badge bg-green-50 text-green-700 border-green-200">En línea</span>
                  : <span className="badge bg-slate-100 text-slate-600 border-slate-200">Sin señal</span>}</td>
              </tr>
            ))}
            {sim.spare.map((d) => (
              <tr key={d.id} className="border-b border-slate-50 bg-slate-50/50">
                <td className="td font-mono font-semibold">{d.id}</td>
                <td className="td text-slate-400">Sin asignar</td><td className="td text-slate-400">—</td>
                <td className="td"><BatteryPill level={d.battery} /></td><td className="td text-slate-400">—</td>
                <td className="td text-slate-600">{d.firmware}</td>
                <td className="td"><span className="badge bg-slate-100 text-slate-600 border-slate-200">Bodega</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
