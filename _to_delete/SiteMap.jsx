import { MapContainer, TileLayer, Rectangle, CircleMarker, Tooltip } from 'react-leaflet';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { ZONES, SITE } from '../data/seed';
import { STATUS, STATUS_RANK } from '../lib/risk';

export default function SiteMap({ height = 460, focusWorkerId }) {
  const { workers, workerStatus } = useApp();
  const navigate = useNavigate();

  const zoneColor = (zone) => {
    if (zone.kind === 'descanso') return '#0891b2';
    const worst = workers.filter((w) => w.zoneId === zone.id).reduce((m, w) => Math.max(m, STATUS_RANK[w.status]), 1);
    return worst === 3 ? '#dc2626' : worst === 2 ? '#2563eb' : '#16a34a';
  };

  return (
    <MapContainer center={SITE.center} zoom={18} maxZoom={20} style={{ height, width: '100%', borderRadius: 12 }} scrollWheelZoom>
      <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={20} maxNativeZoom={19} />
      {ZONES.map((z) => (
        <Rectangle key={z.id} bounds={[[z.bounds[0], z.bounds[1]], [z.bounds[2], z.bounds[3]]]}
          pathOptions={{ color: zoneColor(z), weight: 2, fillOpacity: 0.12, dashArray: z.kind === 'descanso' ? '6 4' : undefined }}>
          <Tooltip sticky direction="top">{z.name}</Tooltip>
        </Rectangle>
      ))}
      {workers.map((w) => {
        const st = workerStatus(w);
        const focus = w.id === focusWorkerId;
        return (
          <CircleMarker key={w.id} center={w.pos} radius={focus ? 11 : w.incident ? 10 : w.status === 'alerta' ? 8 : 6}
            pathOptions={{ color: w.incident ? '#111827' : focus ? '#0b2247' : '#fff', weight: w.incident ? 4 : focus ? 3 : 1.5, fillColor: STATUS[st].hex, fillOpacity: 0.95 }}
            eventHandlers={{ click: () => navigate(`/workers/${w.id}`) }}>
            <Tooltip direction="top">
              <b>{w.name}</b><br />{w.trade} · {STATUS[st].label}<br />{w.env.t.toFixed(1)}°C · Riesgo {Math.round(w.score)}
              {w.incident && <><br /><b>{w.incident.type === 'caida' ? 'Posible caída' : `Sin movimiento ${w.stillMin} min`}</b></>}
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
