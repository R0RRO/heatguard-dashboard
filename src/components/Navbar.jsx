import { Link, useLocation } from 'react-router-dom';
import { Flame, Menu, X, LogOut, Bell } from 'lucide-react';
import { useState } from 'react';
import { useApp } from '../context/AppContext';
import { SITE } from '../data/seed';
import ThemeToggle from './ThemeToggle';

export default function Navbar() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const { user, logout, alerts } = useApp();
  const active = alerts.filter((a) => a.status === 'activa' && a.level === 'alerta').length;

  const links = [
    { to: '/', label: 'Panel' },
    { to: '/workers', label: 'Trabajadores' },
    { to: '/map', label: 'Mapa' },
    { to: '/alerts', label: 'Alertas', badge: active },
    { to: '/devices', label: 'Dispositivos' },
    { to: '/producto', label: 'Producto' },
    ...(user.role !== 'supervisor' ? [{ to: '/settings', label: 'Umbrales' }] : []),
  ];
  const isActive = (to) => (to === '/' ? pathname === '/' : pathname.startsWith(to));

  return (
    <nav className="bg-navy-900 sticky top-0 z-[1001] shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-2.5 no-underline">
            <div className="bg-heat-500 rounded-lg p-2"><Flame className="w-5 h-5 text-white" /></div>
            <div className="leading-tight">
              <span className="block text-lg font-extrabold text-white tracking-tight">HEATGUARD <span className="text-heat-400">CLIP</span></span>
              <span className="block text-[10px] text-navy-200 -mt-0.5">{SITE.name}</span>
            </div>
          </Link>

          <div className="hidden xl:flex items-center gap-1">
            {links.map((l) => (
              <Link key={l.to} to={l.to} className={isActive(l.to) ? 'nav-link-active' : 'nav-link'}>
                {l.label}
                {l.badge > 0 && <span className="ml-1.5 bg-red-500 text-white text-[10px] font-bold rounded-full px-1.5 py-0.5">{l.badge}</span>}
              </Link>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Link to="/alerts" className="relative p-2 text-navy-100 hover:text-white xl:hidden">
              <Bell className="w-5 h-5" />
              {active > 0 && <span className="absolute top-0.5 right-0.5 bg-red-500 text-white text-[10px] font-bold rounded-full px-1">{active}</span>}
            </Link>
            <ThemeToggle />
            <div className="hidden sm:block text-right leading-tight">
              <p className="text-sm font-semibold text-white">{user.name}</p>
              <p className="text-[11px] text-navy-200 capitalize">{user.role}</p>
            </div>
            <button onClick={logout} title="Cerrar sesión" className="hidden sm:flex p-2 rounded-lg text-navy-200 hover:bg-white/10 hover:text-white cursor-pointer">
              <LogOut className="w-4 h-4" />
            </button>
            <button onClick={() => setOpen(!open)} className="xl:hidden p-2 rounded-lg text-navy-100 hover:bg-white/10 cursor-pointer">
              {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>
      {open && (
        <div className="xl:hidden border-t border-white/10">
          {links.map((l) => (
            <Link key={l.to} to={l.to} onClick={() => setOpen(false)} className={isActive(l.to) ? 'nav-link-mobile-active' : 'nav-link-mobile'}>
              {l.label}{l.badge > 0 && ` (${l.badge})`}
            </Link>
          ))}
          <button onClick={logout} className="flex items-center gap-2 px-6 py-3 text-sm text-red-300 cursor-pointer"><LogOut className="w-4 h-4" /> Salir</button>
        </div>
      )}
    </nav>
  );
}
