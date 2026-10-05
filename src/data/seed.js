// Datos semilla: una obra ficticia en Santiago de Chile.
export const SITE = {
  name: 'Torre Alameda',
  company: 'Constructora Demo',
  center: [-33.4150, -70.6000],
};

// bounds: [latSur, lngOeste, latNorte, lngEste]
export const ZONES = [
  { id: 'z1', name: 'Losa Piso 12',       kind: 'trabajo',  tempOffset: 3.0,  rhOffset: -4, bounds: [-33.4148, -70.6009, -33.4140, -70.5999], desc: 'Hormigonado a cielo abierto, sin sombra.' },
  { id: 'z2', name: 'Fachada Norte',      kind: 'trabajo',  tempOffset: 2.0,  rhOffset: -2, bounds: [-33.4140, -70.6009, -33.4133, -70.5992], desc: 'Andamios con exposición solar directa.' },
  { id: 'z3', name: 'Excavación Subsuelo', kind: 'trabajo',  tempOffset: -1.5, rhOffset: 8,  bounds: [-33.4158, -70.6009, -33.4148, -70.6000], desc: 'Zona baja, sombreada y con poca ventilación.' },
  { id: 'z4', name: 'Bodega y Acopio',    kind: 'trabajo',  tempOffset: 0.5,  rhOffset: 0,  bounds: [-33.4158, -70.5999, -33.4148, -70.5989], desc: 'Carga y descarga de materiales.' },
  { id: 'z5', name: 'Zona de Descanso',   kind: 'descanso', tempOffset: -5.0, rhOffset: 6,  bounds: [-33.4148, -70.5999, -33.4141, -70.5992], desc: 'Sombra, agua fresca y ventilación.' },
];

const NAMES = [
  'Juan Pérez', 'Miguel Torres', 'Roberto Díaz', 'Luis Gómez', 'Carlos Soto', 'Andrés Muñoz',
  'Felipe Rojas', 'Diego Contreras', 'Sergio Vargas', 'Patricio Silva', 'Jorge Fuentes', 'Héctor Araya',
  'Cristian Núñez', 'Marcelo Tapia', 'Pablo Sepúlveda', 'Ricardo Castillo', 'Manuel Ortiz', 'Nicolás Reyes',
  'Óscar Figueroa', 'Rodrigo Morales', 'Iván Espinoza', 'Claudio Vera', 'Gonzalo Campos', 'Mauricio Lagos',
];
const TRADES = [
  { name: 'Albañil', intensity: 0.7 }, { name: 'Enfierrador', intensity: 0.85 }, { name: 'Carpintero', intensity: 0.65 },
  { name: 'Gruista', intensity: 0.25 }, { name: 'Soldador', intensity: 0.6 }, { name: 'Electricista', intensity: 0.45 },
  { name: 'Jornal', intensity: 0.9 }, { name: 'Operador maquinaria', intensity: 0.3 }, { name: 'Pintor', intensity: 0.5 },
];
const CREWS = ['Cuadrilla A', 'Cuadrilla B', 'Cuadrilla C', 'Cuadrilla D'];

export const WORKER_SEEDS = NAMES.map((name, i) => ({
  id: `w${i + 1}`,
  name,
  trade: TRADES[i % TRADES.length].name,
  intensity: TRADES[(i * 5) % TRADES.length].intensity,
  crew: CREWS[i % CREWS.length],
  zoneId: ['z1', 'z2', 'z3', 'z4'][i % 4],
  deviceId: `HG-${String(101 + i).padStart(4, '0')}`,
  mount: i % 3 === 0 ? 'chaleco' : 'casco',
}));

// Clips en bodega (sin asignar)
export const SPARE_DEVICES = [
  { id: 'HG-0125', battery: 100, firmware: '1.4.2', mount: null },
  { id: 'HG-0126', battery: 82, firmware: '1.4.2', mount: null },
  { id: 'HG-0127', battery: 47, firmware: '1.3.9', mount: null },
];
