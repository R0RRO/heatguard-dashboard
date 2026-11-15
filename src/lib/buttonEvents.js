// Textos de los eventos de pausa (el inicio y el fin se marcan con el botón del clip)
export const BUTTON_EVENT = {
  'pausa-solicitada': { label: 'Toca descanso (clip)', tone: 'bg-red-50 text-red-700' },
  'pausa-inicio': { label: 'Comenzó su pausa', tone: 'bg-blue-50 text-blue-700' },
  'pausa-fin': { label: 'Terminó su pausa', tone: 'bg-green-50 text-green-700' },
};

// Qué hace el botón mantenido ahora
export const buttonAction = (w) => (w.resting ? 'terminar la pausa' : 'comenzar la pausa');
